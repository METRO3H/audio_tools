/**
 * srtStreamParsing.js
 * ────────────────────
 * Funciones puras para leer los logs de stream/input de Translate SRT.
 *
 * Los logs llegan como un solo texto por archivo (ver core/translation/runner.py, que arma los
 * encabezados "═══ Bloque N/M ═══", y model_manager.translate_block, que arma el mensaje del
 * usuario con "[Previous translated context]" y "[Block to translate]").
 */

/**
 * Parte un log en bloques por sus encabezados "═══ Bloque N/M ═══". Lo que haya antes del primer
 * encabezado se descarta; un encabezado sin contenido no genera bloque.
 * @returns {{header: string, content: string}[]}
 */
export function parseBlocks(text) {
   if (!text) return [];
   const blocks = [];
   let currentHeader = "";
   let currentContent = [];
   let inBlock = false;

   const flush = () => {
      if (inBlock && currentContent.length > 0) {
         blocks.push({ header: currentHeader, content: currentContent.join("\n").trim() });
      }
   };

   for (const line of text.split("\n")) {
      if (line.match(/^═══* Bloque/)) {
         flush();
         currentHeader = line.trim();
         currentContent = [];
         inBlock = true;
      } else if (inBlock) {
         currentContent.push(line);
      }
   }
   flush();
   return blocks;
}

/** Contexto previo ("[Previous translated context]") de un mensaje de usuario; "" si no hay. */
export function extractContext(userMessage) {
   if (!userMessage) return "";
   const match = userMessage.match(/\[Previous translated context\]:\s*([\s\S]*?)(?=\n\n\[Block to translate\]|$)/);
   return match ? match[1].trim() : "";
}

/** Bloque a traducir ("[Block to translate]") de un mensaje de usuario; el mensaje entero si no hay marca. */
export function extractBlock(userMessage) {
   if (!userMessage) return "";
   const match = userMessage.match(/\[Block to translate\]:\s*([\s\S]*)/);
   return match ? match[1].trim() : userMessage;
}
