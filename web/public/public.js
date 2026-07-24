/**
 * Public interface entry — citizen chrome only (no admin imports beyond modes).
 */
(function () {
  "use strict";

  EquirouteModes.init("public");
  EquirouteEarth.createApp({
    mode: "public",
    assetBase: EquirouteConfig.assetBase,
  });
})();
