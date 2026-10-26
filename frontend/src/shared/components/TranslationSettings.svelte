<script>
   /**
    * TranslationSettings.svelte
    * ───────────────────────────
    * Modelo + GPU layers/contexto/temperatura, para las 3 tools de traducción
    * (.srt, chapters, filenames). nGpuLayers/nCtx/temperature/selectedModel se
    * guardan por separado según el modo (local vs remoto: los valores pensados
    * para la GPU de esta PC no tienen por qué servir para la del mediador, y
    * viceversa — confirmado al diseñar esto, se mantiene).
    *
    * Dos persisted() fijos, uno por modo, creados los dos desde que el
    * componente arranca: persisted() necesita una clave fija desde la
    * inicialización, y acá el modo (`target.mode`) recién se sabe después de
    * consultar al mediador (async) — por eso no se puede crear uno solo con
    * una clave que dependa de `target.mode`. En vez de eso, los dos existen
    * siempre y `settings` (bindable) apunta al que corresponda.
    *
    * `settings` es el store activo en sí (no una copia): el padre lee y
    * escribe `settings.selectedModel` / `.nGpuLayers` / `.nCtx` / `.temperature`
    * directo (acá mismo, con bind:value) y persisted() ya se encarga de
    * guardarlo solo. No hay efectos de sincronización en ningún sentido —
    * nada que pueda desincronizarse entre sí.
    *
    * Props:
    *   target          el objeto de useExecutionTarget (decide local/remoto)
    *   models           lista de nombres de modelo a mostrar en el combo
    *   storageKey        prefijo de las 2 claves de localStorage, p. ej.
    *                    "translate_srt" -> translate_srt_local_config /
    *                    translate_srt_remote_config
    *   settings          $bindable: el store activo ({selectedModel, nGpuLayers,
    *                    nCtx, temperature}) — undefined hasta que target.mode
    *                    se resuelve
    *   noModelsLabel      texto del combo cuando `models` está vacío
    *   remoteNoModelsHint  texto de aviso (opcional) cuando el modo es remoto y
    *                    `models` está vacío — p. ej. qué carpeta llenar en el mediador
    */

   import { untrack } from "svelte";
   import { persisted } from "@shared/state/persisted.svelte.js";

   let {
      target,
      models = [],
      storageKey,
      settings = $bindable(),
      noModelsLabel = "Sin modelos",
      remoteNoModelsHint = "",
   } = $props();

   // storageKey es fijo por instancia (cada vista pasa un literal, p. ej. "translate_srt"); no
   // está pensado para cambiar en caliente — igual que persisted() en sí, que solo se puede
   // llamar durante la inicialización. untrack() lo deja explícito en vez de que Svelte avise
   // "esto solo captura el valor inicial" como si fuera sin querer.
   const key = untrack(() => storageKey);
   const local = persisted(`${key}_local_config`, {
      selectedModel: "",
      nGpuLayers: 20,
      nCtx: 4096,
      temperature: 0.3,
   });
   const remote = persisted(`${key}_remote_config`, {
      selectedModel: "",
      nGpuLayers: 0,
      nCtx: 4096,
      temperature: 0.3,
   });

   $effect(() => {
      settings = target.mode === "remote" ? remote : target.mode === "local" ? local : undefined;
   });

   // Si no hay modelo elegido todavía, o el guardado ya no está en la lista actual (se borró el
   // .gguf, cambió de PC, el mediador tiene otros...), cae al primero disponible en vez de
   // quedar vacío o apuntando a un modelo fantasma que ya no existe.
   $effect(() => {
      if (settings && models.length && !models.includes(settings.selectedModel)) {
         settings.selectedModel = models[0];
      }
   });
</script>

{#if settings}
   <div class="flex flex-col gap-1.5">
      <span class="text-xs text-white/40">Modelo</span>
      <select
         bind:value={settings.selectedModel}
         class="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2
            text-xs text-white outline-none focus:border-indigo-500/50 transition-colors cursor-pointer"
      >
         {#if !models.length}
            <option value="">{noModelsLabel}</option>
         {/if}
         {#each models as m (m)}
            <option value={m}>{m}</option>
         {/each}
      </select>
      {#if target.mode === "remote" && !models.length && remoteNoModelsHint}
         <span class="text-xs text-yellow-400">{remoteNoModelsHint}</span>
      {/if}
   </div>

   <div class="grid grid-cols-3 gap-3">
      <div class="flex flex-col gap-1.5">
         <label class="text-[11px] text-white/40" for="translationSettingsGpuLayers">GPU layers</label>
         <input
            id="translationSettingsGpuLayers"
            type="number"
            bind:value={settings.nGpuLayers}
            min="0"
            class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5
               text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors"
         />
      </div>
      <div class="flex flex-col gap-1.5">
         <label class="text-[11px] text-white/40" for="translationSettingsCtx">Contexto</label>
         <input
            id="translationSettingsCtx"
            type="number"
            bind:value={settings.nCtx}
            min="512"
            step="512"
            class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5
               text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors"
         />
      </div>
      <div class="flex flex-col gap-1.5">
         <label class="text-[11px] text-white/40" for="translationSettingsTemp">Temperatura</label>
         <input
            id="translationSettingsTemp"
            type="number"
            bind:value={settings.temperature}
            min="0"
            max="2"
            step="0.1"
            class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5
               text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors"
         />
      </div>
   </div>
{/if}
