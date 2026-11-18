import assert from "node:assert/strict";
import { test } from "node:test";
import { ProfileSaveQueue } from "../lib/profileSaveQueue.ts";

const tick = () => new Promise((resolve) => setTimeout(resolve, 5));
test("rapid edits persist only the latest pending snapshot", async () => {
  const writes: string[] = [];
  const queue = new ProfileSaveQueue<string>(async (value) => { writes.push(value); }, 0);
  const results = await Promise.all([queue.save("a"), queue.save("ab"), queue.save("abc")]);
  assert.deepEqual(writes, ["abc"]);
  assert.deepEqual(results, [true, true, true]);
});
test("writes never overlap; later edits wait behind the active request", async () => {
  const writes: string[] = [];
  let finish: (() => void) | undefined;
  const queue = new ProfileSaveQueue<string>(async (value) => {
    writes.push(value);
    if (value === "first") await new Promise<void>((resolve) => { finish = resolve; });
  }, 0);
  const first = queue.save("first");
  await tick();
  const second = queue.save("second");
  const third = queue.save("third");
  assert.deepEqual(writes, ["first"]);
  finish!();
  assert.deepEqual(await Promise.all([first, second, third]), [true, true, true]);
  assert.deepEqual(writes, ["first", "third"]);
});
test("failed writes report failure and allow a successful retry", async () => {
  let fail = true;
  const queue = new ProfileSaveQueue<string>(async () => { if (fail) throw new Error("offline"); }, 0);
  assert.equal(await queue.save("latest"), false);
  fail = false;
  assert.equal(await queue.save("latest"), true);
});
test("account change cancels pending saves without sending them", async () => {
  const writes: string[] = [];
  const queue = new ProfileSaveQueue<string>(async (value) => { writes.push(value); });
  const pending = queue.save("old account");
  queue.cancel();
  assert.equal(await pending, false);
  assert.equal(await queue.save("new edit"), false);
  assert.deepEqual(writes, []);
});
test("navigation flush preserves the latest pending edit", async () => {
  const writes: string[] = [];
  const queue = new ProfileSaveQueue<string>(async (value) => { writes.push(value); }, 10000);
  const pending = queue.save("keep on navigation");
  queue.flush();
  assert.equal(await pending, true);
  assert.deepEqual(writes, ["keep on navigation"]);
});
