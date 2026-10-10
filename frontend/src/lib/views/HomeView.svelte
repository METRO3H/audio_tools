<script>
   /**
    * HomeView.svelte
    * ────────────────
    * Pantalla de inicio. Muestra las cards de cada herramienta
    * y permite al usuario elegir con cuál trabajar.
    *
    * Props:
    *   navigate  function(view) — callback para cambiar de vista
    */

   import ToolCard from "$lib/components/ToolCard.svelte";
   import { appConfig } from "$lib/stores/config.svelte.js";
   import { bridge } from "$lib/stores/bridge.svelte.js";

   let { navigate } = $props();

   // ── Carpeta base ────────────────────────────────────────────────────────────

   async function pickBaseFolder() {
      const folder = await bridge.pick_folder();
      if (folder) appConfig.setBaseFolder(folder);
   }

   // ── Herramientas disponibles ────────────────────────────────────────────────

   const tools = [
      {
         id: "merge",
         title: "Merge",
         description: "Fusiona varios archivos de audio en uno solo con capítulos.",
         icon: "🔗",
      },
      {
         id: "diverge",
         title: "Diverge",
         description: "Divide un archivo de audio en segmentos de igual duración.",
         icon: "✂️",
      },
      {
         id: "audio_to_video",
         title: "Audio → Video",
         description: "Convierte archivos de audio a video con imagen de fondo.",
         icon: "🎬",
      },
      {
         id: "transcribe",
         title: "Transcribe",
         description: "Genera subtítulos .srt usando faster-whisper.",
         icon: "📝",
      },
      {
         id: "translate",
         title: "Translate",
         description: "Traduce subtítulos .srt con un LLM local.",
         icon: "🌐",
      },
   ];
</script>

<div class="flex h-full flex-col">
   <!-- Header -->
   <header class="flex items-center justify-between px-8 py-6 border-b border-white/5">
      <div>
         <h1 class="text-lg font-semibold tracking-tight">Audio Tools</h1>
         <p class="text-xs text-white/30 mt-0.5">Selecciona una herramienta para comenzar</p>
      </div>

      <!-- Carpeta base -->
      <button
         class="flex items-center gap-2 rounded-lg border border-white/10
             bg-white/5 px-3 py-1.5 text-xs text-white/50
             hover:border-white/20 hover:text-white/70 transition-all"
         onclick={pickBaseFolder}
         title="Cambiar carpeta base"
      >
         <span>📁</span>
         <span class="max-w-48 truncate">
            {appConfig.baseFolder || "Sin carpeta base"}
         </span>
      </button>
   </header>

   <!-- Grid de herramientas -->
   <main class="flex-1 overflow-y-auto px-8 py-8">
      <div class="grid grid-cols-2 gap-4 max-w-2xl mx-auto lg:grid-cols-3">
         {#each tools as tool (tool.id)}
            <ToolCard
               title={tool.title}
               description={tool.description}
               icon={tool.icon}
               onclick={() => navigate(tool.id)}
            />
         {/each}
      </div>
   </main>
</div>
