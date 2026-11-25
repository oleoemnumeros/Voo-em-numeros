/* Voo em Números: escolha "De" e "Para" e vá direto para a página da rota */
(function () {
  "use strict";
  function ini(box) {
    var d;
    try { d = JSON.parse(box.getAttribute("data-rotas")); } catch (e) { return; }
    var de = box.querySelector(".rs-de"), para = box.querySelector(".rs-para"), ir = box.querySelector(".rs-ir");
    var ord = function (a, b) { return d.a[a].localeCompare(d.a[b], "pt-BR"); };
    function opt(sel, txt, val) { var o = document.createElement("option"); o.value = val; o.textContent = txt; sel.appendChild(o); }
    opt(de, "Escolha a origem", "");
    Object.keys(d.r).sort(ord).forEach(function (k) { opt(de, d.a[k], k); });
    function enche() {
      para.innerHTML = "";
      var lst = d.r[de.value] || [];
      opt(para, de.value ? "Escolha o destino" : "Escolha a origem antes", "");
      lst.slice().sort(function (x, y) { return ord(x[0], y[0]); }).forEach(function (x) { opt(para, d.a[x[0]], x[1]); });
      para.disabled = !de.value;
      ir.disabled = true;
    }
    de.addEventListener("change", function () { enche(); if (de.value) para.focus(); });
    para.addEventListener("change", function () { ir.disabled = !para.value; if (para.value) location.href = "/rotas/" + para.value + "/"; });
    ir.addEventListener("click", function () { if (para.value) location.href = "/rotas/" + para.value + "/"; });
    enche();
    box.hidden = false;
  }
  function tudo() { var l = document.querySelectorAll("[data-rotas]"); for (var i = 0; i < l.length; i++) ini(l[i]); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", tudo); else tudo();
})();
