/* Voo em Números: "onde o meu preço fica na curva?" (usa os dados do atributo data-pr de cada bloco) */
(function () {
  "use strict";
  var fmt = function (v) { return v.toLocaleString("pt-BR", { maximumFractionDigits: 0 }); };
  function lim(e, i) { return i + 1 < e.length ? e[i + 1] : e[i] * 1.5; }
  function cdf(c, e, x) {
    var tot = 0, acc = 0, i;
    for (i = 0; i < c.length; i++) tot += c[i];
    if (!tot) return 0;
    for (i = 0; i < c.length; i++) {
      var lo = e[i], hi = lim(e, i);
      if (x >= hi) acc += c[i];
      else if (x > lo) { acc += c[i] * (x - lo) / (hi - lo); break; }
      else break;
    }
    return acc / tot;
  }
  function num(s) {
    s = String(s).replace(/R\$|\s/g, "");
    if (!s) return NaN;
    if (s.indexOf(",") > -1) s = s.replace(/\./g, "").replace(",", ".");
    else if (/^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "");
    return parseFloat(s);
  }
  function faixa(p) {
    if (p <= 0.10) return ["muito barato", "good"];
    if (p <= 0.25) return ["barato", "good"];
    if (p <= 0.75) return ["normal", ""];
    if (p <= 0.90) return ["caro", "bad"];
    return ["muito caro", "bad"];
  }
  function ini(box) {
    var cfg;
    try { cfg = JSON.parse(box.getAttribute("data-pr")); } catch (e) { return; }
    var ctl = box.querySelector(".pr-ctl"), inp = box.querySelector(".pr-in"), sel = box.querySelector(".pr-sel"),
        res = box.querySelector(".pr-res"), svgs = box.querySelectorAll(".pr-svg");
    if (!ctl || !inp) return;
    ctl.hidden = false;
    function atual() { return cfg.d[sel ? sel.value : ""]; }
    function mostra() {
      var k = sel ? sel.value : "";
      for (var i = 0; i < svgs.length; i++) svgs[i].hidden = svgs[i].getAttribute("data-k") !== k;
    }
    function calc() {
      mostra();
      var d = atual(), v = num(inp.value), svg = box.querySelector('.pr-svg[data-k="' + (sel ? sel.value : "") + '"]');
      var m = svg && svg.querySelector(".pr-m"), t = svg && svg.querySelector(".pr-mt");
      if (!isFinite(v) || v <= 0) {
        res.className = "pr-res";
        res.textContent = "Digite o preço que você viu para ver onde ele fica na curva.";
        if (m) { m.setAttribute("visibility", "hidden"); t.setAttribute("visibility", "hidden"); }
        return;
      }
      var p = cdf(d.c, cfg.e, v), f = faixa(p), mais = Math.round((1 - p) * 100), menos = Math.round(p * 100);
      var quem = sel && sel.value ? " da " + d.nome : "";
      var txt = "R$ " + fmt(v) + " é um preço " + f[0] + ". ";
      if (p <= 0.5) txt += "Fica abaixo de " + (100 - menos) + "% dos bilhetes" + quem + " vendidos em " + cfg.m + ".";
      else txt += "Fica acima de " + menos + "% dos bilhetes" + quem + " vendidos em " + cfg.m + ".";
      if (v >= cfg.e[cfg.e.length - 1]) txt = "R$ " + fmt(v) + " está entre os preços mais altos desta rota em " + cfg.m + ".";
      res.className = "pr-res " + f[1];
      res.textContent = txt + (mais === 0 && p < 1 ? "" : "");
      if (m) {
        var x = d.a + (Math.min(Math.max(v, d.x0), d.x1) - d.x0) / (d.x1 - d.x0) * (d.b - d.a);
        m.setAttribute("x1", x); m.setAttribute("x2", x); m.removeAttribute("visibility");
        t.setAttribute("x", Math.min(Math.max(x, 40), 680)); t.textContent = "R$ " + fmt(v); t.removeAttribute("visibility");
      }
    }
    inp.addEventListener("input", calc);
    if (sel) sel.addEventListener("change", calc);
  }
  function tudo() { var l = document.querySelectorAll(".pr[data-pr]"); for (var i = 0; i < l.length; i++) ini(l[i]); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", tudo); else tudo();
})();
