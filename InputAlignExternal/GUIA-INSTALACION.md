<!-- coderabbit-ai-generated:v1 -->

# Input Align External: instalar y usar

## Antes de empezar

Este paquete experimental está destinado a **Windows x64, Geometry Dash 2.2081 y Geode 5.11.2**. Incluye el mod compilado original y una carpeta con el simulador actualizado. No necesitas instalar Python aparte. No se ha probado esta actualización dentro del juego real.

Desactiva el InputAlign original, otros buffers de entrada y CBF para esta prueba. Si CBF está cargado, la corrección se suspende.

## Instalación

1. Cierra Geometry Dash. Extrae **todo** el ZIP en una carpeta normal.
2. Copia `sketch.inputalign_external.geode` a `Geometry Dash/geode/mods/`. La ruta es la carpeta del juego; conserva los demás archivos que ya tengas ahí.
3. Abre Geometry Dash con Geode 5.11.2, entra en un nivel y pulsa pausa. Abre el botón **IAX** y selecciona **Abrir CMD**. Si es la primera vez, se abrirá la carpeta `worker` del mod.
4. En el ZIP extraído, abre `InputAlignWorker`. Copia **el contenido de esa carpeta** dentro de la carpeta `worker` que abrió el juego. Deben quedar allí `python.exe`, `python312.zip`, `gdsim.dll`, `main.py`, `predictor.py`, las carpetas `vendor` y todos los demás archivos del paquete. No copies una carpeta `InputAlignWorker` dentro de `worker`.
5. Vuelve al juego y pulsa **Abrir CMD** otra vez. Deja la consola abierta y reinicia el intento desde el principio. La consola debe indicar que el simulador está preparado; el panel IAX debe mostrar que está conectado. Cuando cambies de nivel, abre una consola nueva desde IAX.

Si actualizas una instalación anterior y personalizaste `cpu-isolation.json` u `obstacle-sensor.json`, guarda esos dos archivos y restaura tus ajustes después de copiar el paquete.

## Uso y ajustes

- **Shift+Tab** activa o desactiva la corrección dentro del nivel. El panel IAX muestra `ON` o `OFF`. Si Steam intercepta esa combinación, cambia el atajo de su superposición en la configuración de Steam.
- <!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:bc55e5ce42d7853710f34c72043cbc6639037330ea40b9dd1f1c31bece40b7b1 -->

En IAX, abre **Ajustes** (o **Settings** en inglés) para elegir

<!-- /coderabbit-ai-generated:v1 --> `Normal ticks` y `Wave ticks` entre 0 y 400. <!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:d793c9dbf8cd51775104336234d32976fba8362086922d530309b3c01291cd17 -->

La opción `Todo a 400 ticks`

<!-- /coderabbit-ai-generated:v1 --> fija ambos en 400. Un valor mayor exige más trabajo y no garantiza más correcciones.
- El ajuste `Invisible trajectory` debe estar activado para usar la corrección; no dibuja trayectorias. Performance Mode reduce el presupuesto del worker; puede aliviar carga y también terminar menos búsquedas.
- Juega normalmente. El sistema solo puede retrasar una pulsación o liberación que hayas hecho tú. `Corrections` cuenta coincidencias del modelo al aplicar una entrada retrasada; no demuestra por sí solo que se haya evitado una muerte.
- El sensor de obstáculos informa de geometría **ya modelada**. `worker/obstacle-sensor.json` permite ajustar `distance` (30 unidades equivalen a una casilla). Por defecto `limit_search` es `false`; ponerlo en `true` limita cuándo se buscan correcciones y puede hacer perder algunas fuera del radio.

## CPU y cierre

El worker intenta reservar un núcleo físico para sí y separar su afinidad de GD cuando la CPU lo permite. En procesadores híbridos exige elegir un núcleo manualmente; si no puede activarse, la consola informa y sigue funcionando. No cambia la GPU. Puedes desactivarlo poniendo `"enabled": false` en `worker/cpu-isolation.json` antes de abrir la consola. Cierra la consola con **Ctrl+C** para restaurar la afinidad. Si el proceso se termina a la fuerza o se bloquea, reinicia GD para restaurar sus valores predeterminados. No se ha medido el impacto en FPS.

## Si no funciona

- **Abrir CMD muestra la carpeta otra vez:** revisa que `python.exe`, `main.py` y `gdsim.dll` estén directamente en `worker`; copia el contenido completo de `InputAlignWorker`.
- **Consola desconectada:** vuelve a abrirla desde IAX en el nivel actual y reinicia el intento. Deja la ventana abierta.
- **Corrección suspendida / física no coincide:** reinicia el intento y revisa que CBF y otros buffers estén desactivados. Un nivel con mecánicas desconocidas o incompatibles puede seguir rechazándose.
- **Cero correcciones:** puede ser normal si la entrada ya era segura, no se encontró una alternativa dentro del presupuesto o el nivel es incompatible. Prueba un nivel sencillo desde su inicio.

El simulador **no soporta cualquier objeto personalizado**, dual activo o CBF activo. No hay validación sistemática en Geometry Dash real ni garantía de precisión total.
