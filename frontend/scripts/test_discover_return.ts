import assert from "node:assert/strict";
import { discoverReturn } from "../lib/discoverReturn.ts";

const search = "/discover?q=robotics&state=WA&field=Computing&university=Example&verification=Verified&opportunity=Any";
assert.equal(discoverReturn(search), search);
assert.equal(discoverReturn("/discover?q=climate+%26+water"), "/discover?q=climate+%26+water");
for (const value of [undefined, [search], "https://evil.example/discover", "//evil.example/discover", "/\\evil.example/discover", "/account", "javascript:alert(1)"]) {
  assert.equal(discoverReturn(value), "/discover");
}
assert.equal(discoverReturn("/discover#fragment"), "/discover");
console.log("Discover return URL checks passed.");
