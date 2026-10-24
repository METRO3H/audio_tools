<script>
   /**
    * ExecutionModeGate.svelte
    * ─────────────────────────
    * La pantalla previa de las tools que corren en esta PC o en el mediador de la red: dos tarjetas
    * grandes para elegir. Se alimenta de useExecutionTarget.
    *
    *   {#if target.mode === null}
    *      <ExecutionModeGate
    *         title="Transcribe" {goHome} {target}
    *         remoteTitle="Transcribir en remoto" remoteDescription="Usa el server mediador…"
    *         localTitle="Transcribir en esta PC" localDescription="Carga el modelo localmente…"
    *      />
    *   {:else} … {/if}
    *
    * Props:
    *   title, goHome       el encabezado de la vista
    *   target              lo que devuelve useExecutionTarget
    *   remoteTitle, remoteDescription, localTitle, localDescription   los textos de cada tarjeta
    */

   import ViewHeader from "@shared/components/ViewHeader.svelte";
   import Spinner from "@shared/ui/Spinner.svelte";

   let { title, goHome, target, remoteTitle, remoteDescription, localTitle, localDescription } = $props();
</script>

<div class="flex h-full flex-col">
   <ViewHeader {title} {goHome} />

   <main class="flex flex-1 items-center justify-center px-8">
      <div class="flex w-full max-w-2xl items-stretch gap-6">
         <!-- Remoto -->
         <div class="flex flex-1 flex-col gap-2">
            <button
               class="group flex flex-1 flex-col items-center justify-center gap-3
                  rounded-2xl border border-white/10 bg-white/5 p-8 text-center
                  transition-all duration-200 hover:border-white/20 hover:bg-white/10
                  hover:scale-[1.02] active:scale-[0.98] cursor-pointer
                  disabled:cursor-wait disabled:opacity-60 disabled:hover:scale-100"
               onclick={target.selectRemote}
               disabled={target.checking}
            >
               {#if target.checking}
                  <Spinner size={28} />
                  <span class="text-xs text-white/40">Buscando mediador en la red...</span>
               {:else}
                  <span class="text-3xl">🌐</span>
                  <span class="text-sm font-semibold text-white tracking-wide">{remoteTitle}</span>
                  <span class="text-xs text-white/50 leading-relaxed">{remoteDescription}</span>
               {/if}
            </button>
            {#if target.error}
               <span role="alert" class="text-xs text-yellow-400 text-center">{target.error}</span>
            {/if}
         </div>

         <!-- Separador vertical -->
         <div class="w-px self-stretch bg-white/10"></div>

         <!-- Local -->
         <button
            class="group flex flex-1 flex-col items-center justify-center gap-3
               rounded-2xl border border-white/10 bg-white/5 p-8 text-center
               transition-all duration-200 hover:border-white/20 hover:bg-white/10
               hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
            onclick={target.selectLocal}
         >
            <span class="text-3xl">💻</span>
            <span class="text-sm font-semibold text-white tracking-wide">{localTitle}</span>
            <span class="text-xs text-white/50 leading-relaxed">{localDescription}</span>
         </button>
      </div>
   </main>
</div>
