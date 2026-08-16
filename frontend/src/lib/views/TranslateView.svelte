<script>
   import ViewHeader from "$lib/views/shared/ViewHeader.svelte";
   import TranslateSrtView from "$lib/views/shared/TranslateSrtView.svelte";
   import TranslateChaptersView from "$lib/views/shared/TranslateChaptersView.svelte";
   import TranslateFilenamesView from "$lib/views/shared/TranslateFilenamesView.svelte";

   let { goHome } = $props();

   let activeSubTool = $state("menu"); // "menu" | "srt" | "chapters" | "filenames"

   function backToMenu() {
      activeSubTool = "menu";
   }
</script>

{#if activeSubTool === "srt"}
   <TranslateSrtView goHome={backToMenu} />
{:else if activeSubTool === "chapters"}
   <TranslateChaptersView goHome={backToMenu} />
{:else if activeSubTool === "filenames"}
   <TranslateFilenamesView goHome={backToMenu} />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title="Translate" {goHome} />

      <main class="flex flex-1 flex-col items-center justify-center px-8 py-10">
         <div class="flex w-full max-w-md flex-col gap-3">
            <button
               class="flex flex-col gap-1 rounded-xl border border-white/10 bg-white/5
                  px-5 py-4 text-left transition-all hover:border-indigo-400/40 hover:bg-white/[0.07]"
               onclick={() => (activeSubTool = "srt")}
            >
               <span class="text-sm font-medium text-white">Traducir .srt</span>
               <span class="text-xs text-white/40">
                  Subtítulos completos, bloque por bloque, con work info y título
               </span>
            </button>

            <button
               class="flex flex-col gap-1 rounded-xl border border-white/10 bg-white/5
                  px-5 py-4 text-left transition-all hover:border-indigo-400/40 hover:bg-white/[0.07]"
               onclick={() => (activeSubTool = "chapters")}
            >
               <span class="text-sm font-medium text-white">Traducir chapters</span>
               <span class="text-xs text-white/40">
                  Títulos de capítulo embebidos en un archivo de audio/video
               </span>
            </button>

            <button
               class="flex flex-col gap-1 rounded-xl border border-white/10 bg-white/5
                  px-5 py-4 text-left transition-all hover:border-indigo-400/40 hover:bg-white/[0.07]"
               onclick={() => (activeSubTool = "filenames")}
            >
               <span class="text-sm font-medium text-white">Traducir nombres de archivo</span>
               <span class="text-xs text-white/40">
                  Escanea una carpeta y renombra lo que no esté en inglés, con confirmación
               </span>
            </button>
         </div>
      </main>
   </div>
{/if}
