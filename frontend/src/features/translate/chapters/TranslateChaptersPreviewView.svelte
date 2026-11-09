<script>
   /**
    * TranslateChaptersPreviewView.svelte
    * ──────────────────────────────────────
    * Lo que traducir Chapters deja ANTES de tocar el disco: título original → traducido por
    * capítulo, de todos los archivos de la cola juntos. El título traducido es editable; cada
    * capítulo tiene su checkbox — solo los marcados se escriben (apply_translated_chapters), el
    * resto conserva su título original tal cual estaba. Nada se escribe hasta "Confirmar".
    *
    * Props:
    *   files       [{ path, name, chapters: [{index,start,end,original_title,translated_title}] }]
    *   onDiscard   () => void   — descarta todo, sin escribir nada, vuelve al formulario
    *   goHome      () => void
    */

   import { untrack } from "svelte";
   import { bridge } from "@shared/services/bridge.svelte.js";
   import { formatDuration } from "@shared/utils.js";

   let { files = [], onDiscard, goHome } = $props();

   // Copia editable local: {path, name, chapters: [{index,start,end,original_title,title,checked}]}
   // — "title" es lo que se termina mandando (arranca igual al traducido, editable a mano).
   // files es la foto del momento en que llegó la vista previa (ver audiotools:chapters:
   // preview_ready): un snapshot a copiar una sola vez al montar, no algo para seguir
   // reactivamente — de ahí el untrack(), igual que storageKey en TranslationSettings.
   let rows = $state(
      untrack(() => files).map((f) => ({
         path: f.path,
         name: f.name,
         chapters: f.chapters.map((ch) => ({ ...ch, title: ch.translated_title, checked: true })),
      })),
   );

   const totalChapters = $derived(rows.reduce((n, f) => n + f.chapters.length, 0));
   const checkedCount = $derived(rows.reduce((n, f) => n + f.chapters.filter((ch) => ch.checked).length, 0));

   function toggleAll(checked) {
      rows = rows.map((f) => ({ ...f, chapters: f.chapters.map((ch) => ({ ...ch, checked })) }));
   }

   let applying = $state(false);
   let applyResult = $state(null); // null | {applied, errors}

   async function confirm() {
      applying = true;
      const items = rows
         .map((f) => ({
            path: f.path,
            chapters: f.chapters
               .filter((ch) => ch.checked)
               .map((ch) => ({ start: ch.start, end: ch.end, title: ch.title })),
         }))
         .filter((f) => f.chapters.length > 0);
      applyResult = await bridge.apply_translated_chapters(items);
      applying = false;
   }
</script>

{#if applyResult}
   <div class="flex h-full flex-col">
      <div class="flex items-center justify-between px-6 py-4 shrink-0">
         <button class="text-white/30 hover:text-white transition-colors text-sm" onclick={goHome}> ← Inicio </button>
         <span class="text-xs text-white/30">Translate — Chapters</span>
      </div>
      <main class="flex flex-1 flex-col items-center justify-center px-8">
         <div class="flex w-full max-w-md flex-col gap-4">
            <div class="flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 px-4 py-3">
               <span class="text-sm text-white/80">
                  {applyResult.applied.length} archivo{applyResult.applied.length === 1 ? "" : "s"} actualizado{applyResult.applied.length === 1 ? "" : "s"}
                  {#if applyResult.errors.length}, {applyResult.errors.length} con error{/if}
               </span>
            </div>
            {#if applyResult.errors.length}
               <ul class="flex flex-col gap-1 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-400">
                  {#each applyResult.errors as err (err.path)}
                     <li class="truncate">{err.path.split(/[/\\]/).pop()}: {err.error}</li>
                  {/each}
               </ul>
            {/if}
            <button
               class="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
               onclick={goHome}
            >
               Volver al inicio
            </button>
         </div>
      </main>
   </div>
{:else}
   <div class="flex h-full flex-col">
      <div class="flex items-center justify-between px-6 py-4 shrink-0">
         <button class="text-white/30 hover:text-white transition-colors text-sm" onclick={goHome}> ← Inicio </button>
         <span class="text-xs text-white/30">Translate — Chapters · vista previa</span>
      </div>

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-6">
         <div class="flex w-full max-w-3xl flex-1 flex-col gap-4">
            <div class="flex items-center justify-between shrink-0">
               <h2 class="text-sm font-semibold text-white">
                  {checkedCount} de {totalChapters} capítulos marcados
               </h2>
               <div class="flex gap-2 text-xs">
                  <button class="text-indigo-400 hover:text-indigo-300 transition-colors" onclick={() => toggleAll(true)}>
                     Marcar todos
                  </button>
                  <span class="text-white/20">·</span>
                  <button class="text-indigo-400 hover:text-indigo-300 transition-colors" onclick={() => toggleAll(false)}>
                     Desmarcar todos
                  </button>
               </div>
            </div>

            <div
               class="flex-1 overflow-y-auto"
               style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
            >
               {#each rows as file (file.path)}
                  <div class="mb-4">
                     <p class="mb-1.5 truncate text-xs font-medium text-white/50">{file.name}</p>
                     <table class="w-full border-separate border-spacing-0 text-xs">
                        <thead>
                           <tr class="text-white/30">
                              <th class="w-7 pb-1 text-left font-normal"></th>
                              <th class="w-14 pb-1 text-left font-normal">Inicio</th>
                              <th class="pb-1 text-left font-normal">Título original</th>
                              <th class="pb-1 text-left font-normal">Título traducido</th>
                           </tr>
                        </thead>
                        <tbody>
                           {#each file.chapters as ch (ch.index)}
                              <tr class={ch.checked ? "hover:bg-white/5" : "opacity-35"}>
                                 <td class="py-1.5 align-middle">
                                    <input type="checkbox" bind:checked={ch.checked} class="accent-indigo-500" />
                                 </td>
                                 <td class="py-1.5 align-middle text-white/30 tabular-nums">{formatDuration(ch.start)}</td>
                                 <td class="max-w-[220px] truncate py-1.5 align-middle text-white/50">{ch.original_title}</td>
                                 <td class="py-1.5 align-middle">
                                    <input
                                       type="text"
                                       bind:value={ch.title}
                                       disabled={!ch.checked}
                                       class="w-full rounded border border-white/10 bg-white/5 px-2 py-1
                                          text-emerald-400/90 outline-none focus:border-indigo-500/50 transition-colors
                                          disabled:opacity-40"
                                    />
                                 </td>
                              </tr>
                           {/each}
                        </tbody>
                     </table>
                  </div>
               {/each}
            </div>

            <div class="flex justify-end gap-2 shrink-0 border-t border-white/5 pt-4">
               <button
                  class="rounded-lg border border-white/10 px-4 py-2 text-xs text-white/60 hover:text-white transition-colors"
                  onclick={onDiscard}
                  disabled={applying}
               >
                  Descartar
               </button>
               <button
                  class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500
                     transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  onclick={confirm}
                  disabled={checkedCount === 0 || applying}
               >
                  {applying ? "Escribiendo..." : `Confirmar y escribir ${checkedCount} capítulo${checkedCount === 1 ? "" : "s"}`}
               </button>
            </div>
         </div>
      </main>
   </div>
{/if}
