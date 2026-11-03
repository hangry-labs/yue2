import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function load(url,blockedStorage=false) {
  const location=new URL(url),window={};
  const context={window,URL,location,history:{state:null,replaceState(_state,_title,value){location.href=value;}},
    document:{querySelector(){return null;},documentElement:{lang:'en'},body:{classList:{contains(){return true;}}}},
    localStorage:{getItem(){if(blockedStorage)throw Error('blocked');return null;},setItem(){if(blockedStorage)throw Error('blocked');}}};
  vm.runInNewContext(readFileSync(new URL('../../examples/locales.js',import.meta.url),'utf8'),context);
  return {...context,i18n:window.YUE2_I18N};
}

test('gallery catalogs cover the same messages and preserve interpolation variables',()=>{
  const {i18n}=load('http://localhost/examples/');
  const keys=Object.keys(i18n.catalogs.en).sort();
  assert(keys.length>90);
  for(const code of Object.keys(i18n.languages)) {
    assert.deepEqual(Object.keys(i18n.catalogs[code]).sort(),keys);
    for(const key of keys)assert.deepEqual((i18n.catalogs[code][key].match(/\{\w+\}/g)||[]).sort(),(key.match(/\{\w+\}/g)||[]).sort());
  }
});

test('explicit gallery locale works with blocked storage and has an English fallback',()=>{
  const {i18n}=load('http://localhost/examples/?lang=ja',true);
  assert.equal(i18n.locale(),'ja');
  assert.equal(i18n.msg('From words to music.'),'言葉から音楽へ。');
  assert.equal(i18n.msg('Original user words'),'Original user words');
  assert.equal(load('http://localhost/examples/?lang=invalid').i18n.locale(),'en');
});

test('gallery locale never rewrites a title, protocol value or lyric filter',()=>{
  const {i18n,location}=load('http://localhost/examples/?lang=en&language=Japanese#hikari-no-platform');
  i18n.setLocale('pl');
  assert.equal(i18n.msg('Now playing: {title}',{title:'[Verse] <b>歌</b> {count}'}),'Teraz odtwarzane: [Verse] <b>歌</b> {count}');
  assert.equal(i18n.msg('full'),'full');
  assert.equal(location.searchParams.get('language'),'Japanese');
  assert.equal(location.hash,'#hikari-no-platform');
});
