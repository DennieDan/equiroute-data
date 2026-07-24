/**
 * Interface mode: "public" | "admin".
 * Admin can flip to public preview without leaving the admin entry.
 */
(function (global) {
  "use strict";

  let mode = "public";

  function apply() {
    document.body.dataset.interface = mode;
    document.body.classList.toggle("interface-admin", mode === "admin");
    document.body.classList.toggle("interface-public", mode === "public");
  }

  const api = {
    init(m) {
      mode = m === "admin" ? "admin" : "public";
      apply();
      return api;
    },
    get() {
      return mode;
    },
    set(m) {
      return api.init(m);
    },
  };

  global.EquirouteModes = api;
})(typeof window !== "undefined" ? window : globalThis);
