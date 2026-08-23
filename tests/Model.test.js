import { describe, it, before } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const code = readFileSync(new URL('../Model.js', import.meta.url), 'utf8').replace(/^\.pragma library\s*\n/, '');
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(code, sandbox);

describe('Model.bucketRes', () => {
  it('buckets by width thresholds (site semantics)', () => {
    assert.equal(sandbox.bucketRes(8000, 4000), '8K+');
    assert.equal(sandbox.bucketRes(5000, 3000), '5K');
    assert.equal(sandbox.bucketRes(4000, 3000), '4K');
    assert.equal(sandbox.bucketRes(3000, 2000), '1440p');
    assert.equal(sandbox.bucketRes(2000, 1200), '1080p');
    assert.equal(sandbox.bucketRes(1300, 800), '720p');
    assert.equal(sandbox.bucketRes(800, 600), '<=720p');
    assert.equal(sandbox.bucketRes(null, 600), null);
  });
});

describe('Model.prep', () => {
  it('computes tier and hay', () => {
    const entries = [{ p: 'dark/green/img.jpg', t: 'Green Hill', tone: 'dark', color: 'green', tags: ['hill'], w: 3840, h: 2160 }];
    sandbox.prep(entries);
    assert.equal(entries[0].tier, '4K');
    assert.ok(entries[0].hay.includes('dark/green/img.jpg'));
    assert.ok(entries[0].hay.includes('green hill'));
    assert.ok(entries[0].hay.includes('hill'));
  });
});

describe('Model.apply', () => {
  let entries;
  before(() => {
    entries = [
      { p: 'a', t: 'Dark Forest', tone: 'dark', color: 'green', tags: [], w: 3840, h: 2160 },
      { p: 'b', t: 'Light Desert', tone: 'light', color: 'orange', tags: [], w: 1920, h: 1080 },
      { p: 'c', t: 'Green Meadow', tone: 'dark', color: 'green', tags: ['meadow'], w: 6000, h: 4000 },
    ];
    sandbox.prep(entries);
  });
  it('filters by q across path+title+tags', () => {
    let r = sandbox.apply(entries, 'forest', '', '', '', '');
    assert.equal(r.filtered.length, 1);
    assert.equal(entries[r.filtered[0]].t, 'Dark Forest');
    r = sandbox.apply(entries, 'meadow', '', '', '', '');
    assert.equal(r.filtered.length, 1);
  });
  it('filters by tone', () => {
    const r = sandbox.apply(entries, '', 'dark', '', '', '');
    assert.equal(r.filtered.length, 2);
  });
  it('filters by color and live facets', () => {
    const r = sandbox.apply(entries, '', '', 'green', '', '');
    assert.equal(r.filtered.length, 2);
    assert.equal(r.facets.color.green, 2);
    assert.equal(r.facets.tone.dark, 2);
  });
  it('filters by resolution range >= and <=', () => {
    let r = sandbox.apply(entries, '', '', '', '4K', '');
    assert.equal(r.filtered.length, 2);
    r = sandbox.apply(entries, '', '', '', '', '1080p');
    assert.equal(r.filtered.length, 1);
  });
});

describe('Model.variant helpers', () => {
  it('variantKeys respects VARIANT_ORDER', () => {
    const e = { th: { aether: {}, palette: {}, material: {} } };
    const got = sandbox.variantKeys(e);
    // cross-realm array: compare via JSON
    assert.equal(JSON.stringify(got), JSON.stringify(['palette','material','aether']));
  });
  it('titleCase', () => {
    assert.equal(sandbox.titleCase('mate-02-aether'), 'Mate 02 Aether');
    assert.equal(sandbox.titleCase('a_b-c'), 'A B C');
  });
});
