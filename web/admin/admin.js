/**
 * Admin interface entry — can preview the public interface chrome.
 */
(function () {
  "use strict";

  EquirouteModes.init("admin");
  EquirouteEarth.createApp({
    mode: "admin",
    assetBase: EquirouteConfig.assetBase,
  });

  const previewBtn = document.getElementById("previewPublicBtn");
  const exitBtn = document.getElementById("exitPreviewBtn");

  function setPreview(on) {
    EquirouteModes.set(on ? "public" : "admin");
    if (previewBtn) previewBtn.hidden = on;
    if (exitBtn) exitBtn.hidden = !on;
  }

  if (previewBtn)
    previewBtn.onclick = () => {
      setPreview(true);
    };
  if (exitBtn)
    exitBtn.onclick = () => {
      setPreview(false);
    };
})();
