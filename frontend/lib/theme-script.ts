// Runs before paint. Only the color preference is stored; no account data.
export const THEME_SCRIPT = String.raw`(function(){
  var key='rmf-theme';
  var media=window.matchMedia('(prefers-color-scheme: dark)');
  function saved(){try{return localStorage.getItem(key);}catch(e){return null;}}
  function apply(value){document.documentElement.dataset.theme=value==='dark'?'dark':'light';}
  function preferred(){var value=saved();return value==='dark'||value==='light'?value:media.matches?'dark':'light';}
  apply(preferred());
  var transitionTimer;
  document.addEventListener('click',function(event){
    var target=event.target;
    if(!(target instanceof Element)||!target.closest('button[data-theme-toggle]'))return;
    var value=document.documentElement.dataset.theme==='dark'?'light':'dark';
    clearTimeout(transitionTimer);
    document.documentElement.classList.add('theme-transition');
    apply(value);try{localStorage.setItem(key,value);}catch(e){}
    transitionTimer=setTimeout(function(){document.documentElement.classList.remove('theme-transition');},280);
  });
  window.addEventListener('storage',function(event){if(event.key===key||event.key===null)apply(preferred());});
  media.addEventListener('change',function(){if(saved()!=='dark'&&saved()!=='light')apply(preferred());});
})();`;
