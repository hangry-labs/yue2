#pragma once
// One bounded FIFO compute worker. HTTP threads never access model state.
#include "results.h"
#include <atomic>
#include <condition_variable>
#include <deque>
#include <thread>
#include <cstdio>

namespace yue_server {
enum class JobStatus { QUEUED, RUNNING, DONE, FAILED, CANCELLED };
inline const char * job_status_str(JobStatus s) {
    switch (s) {
        case JobStatus::QUEUED: return "queued";
        case JobStatus::RUNNING: return "running";
        case JobStatus::DONE: return "done";
        case JobStatus::FAILED: return "failed";
        default: return "cancelled";
    }
}
struct Job {
    std::string id, kind, metrics_json, error;
    std::chrono::steady_clock::time_point submitted = std::chrono::steady_clock::now();
    std::atomic<JobStatus> status{JobStatus::QUEUED};
    std::atomic<bool> cancel{false};
};
struct QueueFull : yue_agent::RetryableError { using RetryableError::RetryableError; };
inline constexpr int RETRY_SECONDS = 5;
class Queue {
    struct Entry { std::shared_ptr<Job> job; std::function<void(std::shared_ptr<Job>)> run; };
    mutable std::mutex mutex_;
    std::condition_variable ready_;
    std::deque<Entry> waiting_;
    std::shared_ptr<Job> active_;
    std::map<std::string, std::shared_ptr<Job>> jobs_;
    std::deque<std::string> history_;
    size_t limit_;
    uint64_t rejected_ = 0, completed_ = 0, failed_ = 0, cancelled_ = 0;
    bool stopping_ = false;
    std::thread worker_;
    void trim_locked() {
        while (history_.size() > 256) { jobs_.erase(history_.front()); history_.pop_front(); }
    }
    void terminal_locked(const std::shared_ptr<Job> & job) {
        auto s = job->status.load();
        if (s == JobStatus::DONE) ++completed_;
        else if (s == JobStatus::CANCELLED) ++cancelled_;
        else ++failed_;
        history_.push_back(job->id); trim_locked();
    }
    void work() {
        for (;;) {
            Entry entry;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                ready_.wait(lock, [&] { return stopping_ || !waiting_.empty(); });
                if (stopping_) return;
                entry = std::move(waiting_.front()); waiting_.pop_front();
                active_ = entry.job; entry.job->status.store(JobStatus::RUNNING);
            }
            try { entry.run(entry.job); }
            catch (const std::exception & e) {
                std::fprintf(stderr, "[Server] Job %s failed: %s\n", entry.job->id.c_str(), e.what());
                entry.job->error = e.what(); entry.job->status.store(JobStatus::FAILED);
            }
            catch (...) { entry.job->error = "Unexpected worker failure"; entry.job->status.store(JobStatus::FAILED); }
            if (entry.job->status.load() == JobStatus::RUNNING)
                entry.job->status.store(entry.job->cancel.load() ? JobStatus::CANCELLED : JobStatus::FAILED);
            {
                std::lock_guard<std::mutex> lock(mutex_);
                terminal_locked(entry.job); active_.reset();
            }
        }
    }
public:
    explicit Queue(size_t limit = 8) : limit_(limit), worker_([this] { work(); }) {}
    ~Queue() { stop(); }
    Queue(const Queue &) = delete;
    Queue & operator=(const Queue &) = delete;
    std::shared_ptr<Job> submit(const std::string & kind, std::function<void(std::shared_ptr<Job>)> run) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopping_ || waiting_.size() + (active_ ? 1 : 0) >= limit_) {
            ++rejected_; throw QueueFull("Generation queue is full; retry after 5 seconds with exponential backoff and jitter");
        }
        auto job = std::make_shared<Job>();
        do { job->id = yue_agent::token().substr(0, 16); } while (jobs_.count(job->id));
        job->kind = kind;
        jobs_.emplace(job->id, job); waiting_.push_back({job, std::move(run)}); ready_.notify_one();
        return job;
    }
    std::shared_ptr<Job> find(const std::string & id) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = jobs_.find(id); return it == jobs_.end() ? nullptr : it->second;
    }
    void note_rejection() { std::lock_guard<std::mutex> lock(mutex_); ++rejected_; }
    void require_capacity() {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopping_ || waiting_.size() + (active_ ? 1 : 0) >= limit_) {
            ++rejected_;
            throw QueueFull("Generation queue is full; retry after 5 seconds with backoff");
        }
    }
    bool cancel(const std::string & id) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = jobs_.find(id); if (it == jobs_.end()) return false;
        auto job = it->second; auto state = job->status.load();
        if (state != JobStatus::QUEUED && state != JobStatus::RUNNING) return true;
        job->cancel.store(true);
        for (auto item = waiting_.begin(); item != waiting_.end(); ++item) {
            if (item->job == job) {
                waiting_.erase(item); job->status.store(JobStatus::CANCELLED); terminal_locked(job); break;
            }
        }
        return true;
    }
    size_t position(const std::string & id) const {
        std::lock_guard<std::mutex> lock(mutex_);
        size_t i = 1;
        for (auto & entry : waiting_) { if (entry.job->id == id) return i; ++i; }
        return 0;
    }
    std::string snapshot() const {
        std::lock_guard<std::mutex> lock(mutex_);
        Json j; auto pending = waiting_.size() + (active_ ? 1 : 0);
        j.integer("limit", (int64_t) limit_); j.integer("pending", (int64_t) pending);
        j.integer("queued", (int64_t) waiting_.size()); j.integer("active", active_ ? 1 : 0);
        j.integer("available", (int64_t) (limit_ - pending)); j.boolean("accepting", !stopping_ && pending < limit_);
        j.integer("retry_after_seconds", RETRY_SECONDS); j.integer("rejected", (int64_t) rejected_);
        j.integer("completed", (int64_t) completed_); j.integer("failed", (int64_t) failed_);
        j.integer("cancelled", (int64_t) cancelled_);
        // Aggregate operations only: never publish other callers' ids/prompts.
        j.text("active_operation", active_ ? active_->kind : "");
        return j.dump();
    }
    void request_stop() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stopping_ = true;
            if (active_) active_->cancel.store(true);
            for (auto & entry : waiting_) {
                entry.job->cancel.store(true); entry.job->status.store(JobStatus::CANCELLED); terminal_locked(entry.job);
            }
            waiting_.clear();
        }
        ready_.notify_all();
    }
    void stop() { request_stop(); if (worker_.joinable()) worker_.join(); }
};
// Keep synchronous waiters below HTTP worker capacity. Excess callers fail
// immediately, leaving threads available for cancellation, discovery and health.
class Slots {
    std::atomic<size_t> used_{0};
    size_t limit_;
public:
    explicit Slots(size_t limit) : limit_(limit) {}
    struct Lease {
        Slots & owner;
        explicit Lease(Slots & s) : owner(s) {}
        ~Lease() { --owner.used_; }
    };
    std::shared_ptr<Lease> acquire() {
        auto used = used_.load();
        while (used < limit_) {
            if (used_.compare_exchange_weak(used, used + 1)) {
                try { return std::make_shared<Lease>(*this); }
                catch (...) { --used_; throw; }
            }
        }
        return nullptr;
    }
    size_t used() const { return used_.load(); }
};
}
