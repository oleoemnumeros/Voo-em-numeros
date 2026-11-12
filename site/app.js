(function(){
  "use strict";
  var busca=document.getElementById("busca");
  if(!busca)return;
  var idx=null, out=document.getElementById("busca-res"), carregando=false;
  function norm(s){return String(s).normalize("NFD").replace(/[̀-ͯ]/g,"").toLowerCase().replace(/\s+/g," ");}
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
  function roda(){
    var q=norm(busca.value).trim();
    if(q.length<2){out.innerHTML="";return;}
    var qs=q.replace(/\s/g,"");
    var r=[];
    for(var i=0;i<idx.length&&r.length<12;i++){
      var p=idx[i], t=norm(p[0]);
      if(t.indexOf(q)>=0||t.replace(/\s/g,"").indexOf(qs)>=0)r.push(p);
    }
    out.innerHTML=r.length?"<ul>"+r.map(function(p){return "<li><a href=\""+p[2]+"\">"+esc(p[0])+" <span>"+esc(p[1])+"</span></a></li>";}).join("")+"</ul>":"<p class=\"small\">Nada encontrado. Tente o código do aeroporto (GRU), a cidade ou o número do voo (LA 3300).</p>";
  }
  function carrega(){
    if(idx||carregando)return;
    carregando=true;
    fetch("/busca.json").then(function(r){return r.json();}).then(function(j){idx=j;roda();}).catch(function(){out.innerHTML="<p class=\"small\">A busca não carregou. Tente recarregar a página.</p>";});
  }
  busca.addEventListener("focus",carrega);
  busca.addEventListener("input",function(){if(idx){roda();}else{carrega();}});
})();
