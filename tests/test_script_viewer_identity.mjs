import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';

// The local integration owns this sibling viewer; use its actual source.
const path = new URL('../fimrun/micromagnetics/viewer/identity.js', import.meta.url);
const {fields, acceptScriptState, checkScriptFrame, selectScriptFrame} = await import(
  'data:text/javascript;base64,' + readFileSync(path).toString('base64'));
const expected = new URLSearchParams({run_id: 'run', instance: 'instance'});
const state = {schema: 'micromagnetics-viewer-v2', version: 2,
  run_id: 'run', instance: 'instance', binding_sha256: 'binding',
  revision: 4, stage_id: 'stage', stage_epoch: 2, case_id: 'case',
  case_identity: 'identity', config_sha256: 'config'};
assert(acceptScriptState(null, state, expected));
assert(acceptScriptState(state, {...state, revision: 5}, expected));
assert(!acceptScriptState(state, {...state, revision: 3}, expected));
assert(!acceptScriptState(state, {...state, stage_epoch: 1, revision: 5}, expected));
assert.throws(() => acceptScriptState(state, {...state, instance: 'old'}, expected));
assert.throws(() => acceptScriptState(state, {...state, run_id: 'other'}, expected));
assert.throws(() => acceptScriptState(state, {...state, config_sha256: 'other'}, expected));
const headers = new Headers({'X-Boris-Schema': 'micromagnetics-frame-v2',
  'X-Boris-Version': '2', 'X-Boris-Frame-Seq': '7'});
for (const field of fields) headers.set('X-Boris-' + field.replaceAll('_', '-'), state[field]);
checkScriptFrame(headers, state, {...state, revision: 5}, 7);
assert.throws(() => checkScriptFrame(headers, state, state, 8));
assert.throws(() => checkScriptFrame(headers, state,
  {...state, stage_id: 'next', stage_epoch: 3, revision: 5}, 7));
for (const field of fields) {
  const bad = new Headers(headers);
  bad.set('X-Boris-' + field.replaceAll('_', '-'), 'wrong');
  assert.throws(() => checkScriptFrame(bad, state, state, 7));
}
console.log('script identity: run/instance/stage/config/sequence rejection and retained same-stage frame pass');

const history = {following: false, requested: 7, frames: [8, 9, 10], latest: 10, sameIdentity: true};
assert.deepEqual(selectScriptFrame(history), {desired: 'latest', target: 10, expired: true});
// A paused recovered frame remains available without repeatedly recovering or following.
assert.deepEqual(selectScriptFrame({...history, requested: 10}), {desired: 10, target: 10, expired: false});
assert.deepEqual(selectScriptFrame({...history, following: true}), {desired: 'latest', target: 10, expired: false});
assert.throws(() => selectScriptFrame({...history, sameIdentity: false}));
assert.throws(() => acceptScriptState(state, {...state, instance: 'replacement'}, expected));
console.log('history: one same-identity selection recovers latest, paused mode retained, cross-domain history rejects');
