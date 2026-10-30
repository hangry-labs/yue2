export interface GpuSample {
	index: number;
	name: string;
	timestamp: number;
	gpu_utilization_percent: number | null;
	memory_utilization_percent: number | null;
	memory_used_mb: number | null;
	memory_total_mb: number | null;
	temperature_c: number | null;
	fan_percent: number | null;
	power_w: number | null;
	power_limit_w: number | null;
	clock_mhz: number | null;
	clock_max_mhz: number | null;
	memory_clock_mhz: number | null;
	memory_clock_max_mhz: number | null;
	performance_state: number | null;
	pcie_generation: number | null;
	pcie_width: number | null;
}
export interface GpuSnapshot {
	gpus: GpuSample[];
	history: GpuSample[];
	message: string;
	sample_interval_seconds: number;
}
