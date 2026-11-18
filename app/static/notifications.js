(() => {
 'use strict';
 const script=document.currentScript, csrf=script.dataset.csrf, user=Number(script.dataset.user);
 const toggle=document.getElementById('notification-toggle'), popover=document.getElementById('notification-popover');
 const lists=[...document.querySelectorAll('[data-notification-list]')];
 const statuses=[...document.querySelectorAll('[data-notification-status],#notification-message')];
 let through=0, busy=false, stopped=false, timer;
 function message(value){statuses.forEach(el=>{el.textContent=value;});}
 function close(){popover.hidden=true;toggle.setAttribute('aria-expanded','false');}
 toggle.addEventListener('click',()=>{const open=popover.hidden;popover.hidden=!open;toggle.setAttribute('aria-expanded',String(open));if(open)refresh();});
 document.addEventListener('click',event=>{if(!event.target.closest('.notification-bell'))close();});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!popover.hidden){close();toggle.focus();}});
 function stop(){stopped=true;clearTimeout(timer);lists.forEach(el=>el.replaceChildren());document.querySelectorAll('[data-notification-count]').forEach(el=>{el.hidden=true;});close();message('Sesi berubah. Muat ulang halaman.');}
 function item(row){
   const article=document.createElement('article');article.className='notification-item'+(row.read?'':' is-unread');article.dataset.notificationId=row.id;
   const dot=document.createElement('span');dot.className='notification-dot';dot.setAttribute('aria-hidden','true');
   const body=document.createElement('div'),link=document.createElement('a'),title=document.createElement('strong'),text=document.createElement('p'),time=document.createElement('time');
   link.href=row.link.startsWith('/')&&!row.link.startsWith('//')?row.link:'/notifikasi';link.dataset.notificationOpen=row.id;
   title.textContent=row.title;text.textContent=row.message;time.textContent=row.created_at;link.append(title);body.append(link,text,time);article.append(dot,body);
   if(!row.read){const button=document.createElement('button');button.type='button';button.className='notification-read';button.dataset.notificationRead=row.id;button.setAttribute('aria-label','Tandai dibaca: '+row.title);button.textContent='✓';article.append(button);}
   return article;
 }
 async function refresh(){
   if(busy||stopped||document.hidden)return;
   busy=true;
   try{
     const response=await fetch('/api/notifikasi',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
     if(response.redirected||response.status===401||response.status===403){stop();return;}
     if(!response.ok)throw new Error();
     const data=await response.json();if(data.user_id!==user){stop();return;}
     through=data.latest_id;
     document.querySelectorAll('[data-notification-count]').forEach(el=>{el.textContent=data.unread>99?'99+':String(data.unread);el.hidden=!data.unread;});
     toggle.setAttribute('aria-label','Notifikasi, '+data.unread+' belum dibaca');
     lists.forEach(list=>{
       // Avoid replacing controls while the user is navigating them with a keyboard.
       if(list.contains(document.activeElement))return;
       const rows=data.items.slice(0,Number(list.dataset.notificationLimit)||5);
       if(rows.length)list.replaceChildren(...rows.map(item));
       else{const empty=document.createElement('p');empty.className='notification-empty';empty.textContent='Belum ada notifikasi.';list.replaceChildren(empty);}
     });
     message('');
   }catch(_){message('Pembaruan tertunda. Sistem akan mencoba lagi.');}
   finally{busy=false;}
 }
 async function mark(url,body){
   if(stopped)return false;
   try{
     const response=await fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({csrf,...body})});
     if(response.redirected){stop();return false;}
     if(!response.ok)throw new Error();
     return true;
   }catch(_){message('Belum dapat menandai notifikasi. Coba lagi.');return false;}
 }
 document.addEventListener('click',async event=>{
   const read=event.target.closest('[data-notification-read]'),open=event.target.closest('[data-notification-open]'),all=event.target.closest('[data-notification-all]');
   if(!read&&!open&&!all)return;
   if(open&&(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey))return;
   event.preventDefault();
   if(all){if(!through)await refresh();if(!through)return;if(await mark('/notifikasi/baca-semua',{through})){all.focus();await refresh();}return;}
   const id=(read||open).dataset[read?'notificationRead':'notificationOpen'];
   if(await mark('/notifikasi/'+id+'/baca',{})){
     document.querySelectorAll('[data-notification-id="'+id+'"]').forEach(el=>{el.classList.remove('is-unread');el.querySelector('[data-notification-read]')?.remove();});
     if(open){location.assign(open.href);return;}
     toggle.focus();await refresh();
   }
 });
 async function poll(){await refresh();if(!stopped)timer=setTimeout(poll,15000);}
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
 window.addEventListener('pagehide',()=>clearTimeout(timer));window.addEventListener('pageshow',event=>{if(event.persisted){stopped=false;poll();}});
 poll();
})();
