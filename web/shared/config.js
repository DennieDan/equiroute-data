/**
 * Shared frontend config stubs.
 * Secrets/tokens that already lived in createApp remain there for this extract;
 * move them here in a later pass if desired.
 */
(function (global) {
  "use strict";

  global.EquirouteConfig = {
    assetBase:
      document.documentElement.dataset.assetBase || "../..",
  };
})(typeof window !== "undefined" ? window : globalThis);
