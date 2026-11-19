<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:4d3be10ef2de7a7212c2229c3f076431a208aaec6bbe6efd8de080421be9073a -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:d21b3b9c76524e802d3788d930e331e8781902c777d27f083147809e070f95d8 -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:fec6f16eace17dac917c40fecf016b823299e816221a232413d98c527586ce58 -->

# Input Align External — alpha 0.3: reparación conservadora

**Actualización de esta continuación:** Stop/Pause/Resume (objeto 1616) se rechaza antes de crear el modelo. El motor heredado selecciona movimientos por grupo de destino, mientras que el manual del editor selecciona los grupos asignados al trigger fuente. Esto retira explícitamente la compatibilidad Stop anunciada en las notas históricas siguientes. No se implementan ni aproximan Pause/Resume. También se suspende el intento si falla la reconstrucción de historial durante la agrupación UDP, conservando el worker para un nuevo intento.

Referencia: [Manual del editor, sección Stop, página impresa 66](https://static.wikia.nocookie.net/geometry-dash/images/8/83/GDEditor-v2.2.pdf/revision/latest?cb=20231220033307). La prueba antigua de igualdad entre motores para Stop se conserva mediante acceso directo al motor; ya no representa autorización de esa mecánica en el predictor.

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:7250c3f6c65cd97b815a9b370cfe16d846441b42c37e895b2e5827942e2b2bd7 -->

La sincronización rechaza paquetes de intentos anteriores y suspende el intento si falla la inicialización o el replay del estado. Durante la agrupación UDP, los paquetes del mismo tick se ordenan también por época de entrada. Estas protecciones evitan reiniciar o reutilizar un estado incompleto; no demuestran equivalencia física con el juego.

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:0f7b336813f8219a0f29830fc4525c5574e3cdcdc00b8ad08cfd2bfc6e0a2a57 -->

El worker conserva como máximo una decisión nativa completada y la reutiliza únicamente ante la misma consulta, estado reconstruido e instancia del simulador. Siempre vuelve a validar el estado real antes de consultar esa caché. Cambiar tick, intento, entrada, época, historial, horizonte o presupuesto evita la reutilización; los resultados incompletos no se almacenan. El horizonte de supervivencia no se reduce.

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:1294d74b4ae01a7c7e509683c314d81fcdc54abb024e0fb816e1cc3f11b6ea98 -->

## Aislamiento de CPU del worker

El paquete añade `cpu_isolation.py` y `cpu-isolation.json` junto a las reparaciones de `main.py` y `predictor.py`. Conserva las DLL originales; no requiere recompilar el mod para esta opción. **No está validado todavía en Windows ni dentro de GD y no hay mediciones nuevas de FPS.**

Al abrir **IAX > Abrir CMD**, el worker intenta separar su afinidad de la de GD: reserva el último núcleo físico completo disponible para la simulación y retira sus hilos SMT de la máscara del juego. Se exigen al menos cuatro núcleos físicos completos disponibles para GD antes de reservar uno. No amplía afinidades existentes. Se mantiene la prioridad Below Normal del worker. No cambia la GPU: gdsim realiza sus cálculos en CPU.

Configura `worker/cpu-isolation.json` **antes de abrir la consola**:

```json
{
  "enabled": true,
  "worker_core": null,
  "game_pid": null
}
```

- `enabled: false` desactiva el aislamiento al siguiente arranque del worker. Para quitar una separación ya activa, cierra con Ctrl+C la consola antes de abrirla de nuevo.
- `worker_core: null` elige automáticamente en CPUs homogéneas. En CPUs híbridas se rechaza la selección automática; el CMD muestra índices, máscaras y clases de los núcleos. Pon el índice físico elegido (por ejemplo `3`), no un número de procesador lógico. No se puede afirmar que reservar un núcleo lento mejore el presupuesto.
- `game_pid: null` usa el proceso padre y comprueba que sea `GeometryDash.exe`. Al arrancar manualmente desde CMD, especifica el PID real de GD. Nunca se modifica cmd.exe por error.
- Alternativa por línea de comandos: `python.exe main.py --bridge "RUTA_DE_DATOS" --cpu-isolation off` o `auto`. La opción prevalece sobre `enabled` en un archivo válido.

Solo se soporta Windows x64 con un grupo de procesadores. Ante configuración inválida, permisos insuficientes, otra consola gestionando el mismo GD o una topología incompatible, se avisa y el worker continúa sin activar aislamiento. Las asignaciones se leen de nuevo tras aplicarlas; un fallo parcial intenta restaurarlas.

Al terminar normalmente, por Ctrl+C o por error Python, se restauran las afinidades originales que sigan coincidiendo con las aplicadas por el worker. Se intenta también al cerrar la ventana. **Terminar el proceso a la fuerza o un crash nativo puede impedir la limpieza: reinicia GD para recuperar su afinidad predeterminada.** Los cambios manuales posteriores de afinidad se conservan.

Esto separa dónde pueden ejecutarse GD y el worker; otros procesos de Windows aún pueden utilizar esos núcleos. Comparten cachés, memoria, energía y temperatura. En 4 núcleos GD queda con 3, lo cual puede empeorar su rendimiento; compara activado/desactivado antes de adoptarlo. No garantiza cumplir 6/3 ms ni eliminar bajones.

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:a2a9009f7a8b4b88858bc5f28ab3be401904abac2d73db4b21b7519b31010eaf -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:83fb01bd78a5c8899ee7fce7fb7f055930e3e3d38ca41d0ed7aa5efcd23cb6b3 -->

## Recuperación de historial con paquetes UDP desordenados

Antes de descartar paquetes, el worker reúne como máximo los mismos 65 paquetes de recepción y ordena los del intento más reciente por tick y época de entrada. Los prefijos observados se reconstruyen con la validación física existente. Esto permite aprovechar un paquete anterior que haya llegado después de otro más reciente; no espera paquetes futuros ni inventa entradas perdidas. El protocolo mantiene sus 64 ticks de historial por paquete y el horizonte permanece intacto.

Si los paquetes disponibles no cubren todo el intervalo o un estado intermedio no coincide, la corrección sigue suspendiéndose. Este cambio mejora tolerancia a reordenación UDP, sin añadir vehículos ni objetos nuevos y sin afirmar una mejora de FPS o cobertura dentro de GD.

## Sensor de obstáculos y distancia ajustable

<!-- /coderabbit-ai-generated:v1 -->

El worker incluye `obstacles.py` y `obstacle-sensor.json`. Detecta sólidos, pendientes y peligros (pinchos, sierras y zonas de daño conocidas) usando sus límites transformados en **el modelo cargado**. No captura hitboxes vivas de GD ni descubre objetos desconocidos de otros mods. Sus resultados aparecen en el estado de IAX y del CMD, actualizado aproximadamente una vez por segundo.

```json
{
  "distance": 600,
  "limit_search": false
}
```

Edita el archivo junto a main.py y reinicia la consola. `distance` admite 0–12000 unidades GD (30 = una casilla). Alternativa: `--obstacle-distance 900` junto a `--bridge`. Se mide la distancia horizontal desde el centro del jugador al borde de la caja envolvente más cercana por delante; incluye cajas que ya cruzan X del jugador. Se ignora Y a propósito: puede detectar suelo, techos y objetos que no vayan a chocar. No es una prueba de peligro.

Con `limit_search: false`, informa sin limitar las búsquedas existentes. Con `true`, omite una búsqueda solo cuando el índice estático no encuentra ningún obstáculo dentro de la distancia. **Esta opción puede perder correcciones útiles**, por ejemplo por límites del escenario, huecos o efectos de un portal fuera del radio. Es una restricción voluntaria de activación; no aumenta por sí misma la compatibilidad física. El estado real se valida también en consultas omitidas. No acorta el horizonte, no aumenta Corrections y no crea pulsaciones.

Si el nivel contiene geometría dinámica, el sensor se declara no disponible y deja continuar la búsqueda normal: no usa posiciones iniciales como si fueran actuales. No modifica el rechazo de mecánicas desconocidas. Portales, pads y orbs no se clasifican como obstáculos de daño/soporte. El índice se prepara una vez y la consulta usa búsqueda binaria; no recorre todos los objetos por tick. La distancia del sensor se añade a la cadencia de estado existente y no genera un paquete por cambio de distancia.

## Estado de la simulación de bloques personalizados

<!-- /coderabbit-ai-generated:v1 -->

Un bloque construido con objetos conocidos conserva las colisiones de sus componentes según el modelo existente: sólidos, pendientes, peligros y sus propiedades admitidas. Su aspecto visual no determina la colisión. Las transformaciones estáticas conocidas ya se procesan; no se ha añadido física nueva en esta actualización.

**No se simula cualquier objeto arbitrario.** Un ID desconocido o una mecánica no modelada suspende la corrección. Rotate/Follow/Scale dinámicos, Area, Keyframe, Touch real, dual y CBF activo siguen fuera. Ignorar esos efectos permitiría dibujar trayectorias, pero violaría la garantía de correcciones verificables.

Para ampliar esa cobertura hacen falta capturas de referencia del juego: colisionadores y transformaciones efectivos, activaciones de triggers y estado físico completo por tick. El protocolo actual no transmite todo ello. Sin esa referencia, ampliar la lista de IDs no demuestra la física de un bloque personalizado. El siguiente paso de implementación debe ser capturar y contrastar esos datos antes de habilitar cada nueva mecánica.

<!-- /coderabbit-ai-generated:v1 -->

<!-- /coderabbit-ai-generated:v1 -->

<!-- /coderabbit-ai-generated:v1 -->


<!-- /coderabbit-ai-generated:v1 -->

<!-- /coderabbit-ai-generated:v1 -->

Mod nuevo y experimental para **Windows x64, Geometry Dash 2.2081 y Geode 5.11.2**. Se distribuye con otra identidad: `sketch.inputalign_external`. No modifica la DLL del InputAlign original ni utiliza su codigo fuente.

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:8c63a8d7edd6004917a5212d4476ab519efdd0d77830ad49e877a8194c44b2d7 -->

## Cambios de 0.2

Se habilitan nave y dash en el puente, ademas de los otros siete modos; hay casos sinteticos de correccion para los ocho vehiculos. El motor externo admite Move, Toggle, Spawn y Stop en sus variantes representadas, asi como teletransporte vertical por portal. Se corrigieron la repeticion de Move por Spawn, el primer Stop, las consultas de colision de ramas diferentes, los objetos dinamicos ya consumidos y la deteccion persistente de un cronograma truncado. El empaquetador verifica los hashes del fork.

Una pulsacion entre pasos fisicos ya no se confunde con divergencia: la entrada actual se aplica en la siguiente simulacion. Una mecanica encontrada solo en una rama hipotetica cancela esa consulta y conserva la sincronizacion del estado real. Esto cambia intencionalmente la politica de 0.1, que bloqueaba el intento. <!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:62297bc4035b3bee467de6ece59b243e228e02b375c04cc9e7cc7f7b9df9315b -->

La biblioteca y los scripts usan el <!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:ba36c815b371184b8b793112d0d5dfe7922880980783c373ef0d3202a546d4cc -->

adaptador version 4

<!-- /coderabbit-ai-generated:v1 --> y el nucleo ABI3; hay que reemplazar **toda** la carpeta de consola al actualizar. La inspeccion admite mas de 128 objetos dinamicos consumidos y el procesamiento de Stop no vuelve a recorrer segmentos ya terminados. En Windows se usa el UCRT del sistema para sin/cos/pow, manteniendo la misma referencia matematica que Python.

<!-- /coderabbit-ai-generated:v1 -->

**Esta version aun no cumple equivalencia total con InputAlign ni garantiza correccion universal.** Tener una tabla de objetos y ocho modos no implementa todos los triggers, dual ni CBF. Las pruebas sinteticas no prueban la fidelidad frente al juego ni los FPS.

## Que hace

<!-- /coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:dce1fc607d74b633f128e11df454188c43552893764047e4df1944ea2e0d1c33 -->

El mod envia estados pequenos por UDP a una consola local. La busqueda de ramas se ejecuta en C++ dentro de `gdsim.dll` en ese proceso; Python gestiona el nivel y la comunicacion. El bucle Python se conserva como referencia independiente para las pruebas, y la consola distribuida exige la DLL ya compilada.

<!-- /coderabbit-ai-generated:v1 --> El simulador independiente busca una pulsacion o liberacion retrasada que sobreviva al horizonte configurado cuando la accion inmediata moriria. El juego usa solo respuestas que ya han llegado, del mismo intento, tick, estado e historial de entradas. No espera a la consola, no ejecuta simulaciones de 400 ticks dentro del juego y no lee memoria de otros procesos.

Una respuesta ausente, tardia o no verificable deja pasar la entrada original. Si se pierde la validacion durante una espera ya iniciada, la entrada pendiente se entrega como entrada original y no se cuenta como correccion verificada. Una nueva accion fisica cancela la anterior pendiente. Una pulsacion muy corta, soltada antes de su turno, puede quedar cancelada por ese comportamiento del buffer. No reproduce macros, ni genera clics sin una entrada tuya previa.

**El contador Corrections cuenta entradas retrasadas con coincidencia del modelo, no muertes evitadas demostradas. No se garantiza una mejora de FPS ni precision perfecta.** La consola consume CPU de otro proceso, con prioridad inferior a la normal. Se mantiene el presupuesto externo predeterminado de 6 ms; Performance Mode lo divide por dos.

## Instalacion del paquete de Windows

1. Desactiva InputAlign original y cualquier otro buffer de entrada. La deteccion de `ai.predictivebuffer` suspende este predictor. Desactiva CBF para probar la correccion.
2. Copia `sketch.inputalign_external.geode` a `Geometry Dash/geode/mods/` y abre el juego con Geode 5.11.2.
3. Entra a un nivel, pausa y pulsa **IAX > Abrir CMD**. La primera vez se abre la carpeta `worker` de datos del mod.
4. Copia **el contenido completo** de `InputAlignWorker` del ZIP dentro de esa carpeta `worker`. Incluye `python.exe`, sus DLL, `python312.zip`, `python312._pth`, `gdsim.dll`, los scripts y `vendor`. No necesitas instalar Python.
5. Vuelve a pulsar **Abrir CMD**, deja la consola abierta y **reinicia el intento desde el principio**. El menu IAX muestra el estado del simulador.
6. Al cambiar de nivel, abre una consola nueva desde IAX. La anterior deja de servir al cerrarse su puente. El boton evita abrir dos consolas del mismo nivel.

Los cambios de configuracion se recargan al pausar y durante el juego. Las grabaciones `attempt-*.json` quedan en **IAX > Carpeta de datos**. Se escriben fuera del hilo del juego y se completan al salir del nivel. <!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:0af9221095570fe68e404522c3f2dad11cd3e322419a6d7ec3bd541e88068b92 -->

La cola esta limitada a 16 archivos pendientes y cada intento a 100000 entradas; si se llena, se descarta la grabacion nueva. Los archivos se publican solo tras cerrar y comprobar la escritura; los incompletos llevan `.partial`. Si falla el disco, se avisa y se retienen hasta 16 intentos en memoria para reintentar al guardar de nuevo. Si el error persiste al salir del nivel, esa memoria se pierde.

<!-- /coderabbit-ai-generated:v1 -->

## Compatibilidad y diferencias conocidas

Se conservan las **38 claves, tipos, rangos y valores predeterminados** del paquete del repositorio, pero esto no es una reproduccion completa de su comportamiento binario:

- `cbf-sync` se conserva como opcion de compatibilidad **reservada**. No implementa sincronizacion CBF. Con CBF detectado, pasos parciales o un paso fisico distinto de 1/240 s, los clics pasan directamente independientemente del valor de esa opcion.
- <!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:a6f21f1381f8b235d45423c0604117961e39c2bfe04f7fa7d3299038a4fc823e -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:3308c8f16449946ee77c093481eed8cf9f8c47d7e0518b8612202445a4fd731c -->

Dual activo, dos jugadores, platformer, start positions activos, checkpoints cargados, teleport orbs con destino de grupo, portales espejo y geometria controlada por triggers no compatibles no reciben correccion. Se permite cargar portales Dual/Solo para predecir prefijos que no los contacten; el primer contacto real suspende el intento, sin reentrada automatica. Los start positions inactivos no rechazan por si solos el nivel. Consulta [IMPLEMENTATION-NOTES.md](IMPLEMENTATION-NOTES.md) para los limites, la cancelacion de consultas y el adaptador v3 requerido.

<!-- /coderabbit-ai-generated:v1 -->

<!-- /coderabbit-ai-generated:v1 --> Un reinicio desde el principio permite volver a sincronizar. <!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:a77a2cf903982d458ae4fea554bb5f87293c7ed89825b76f759a0a88cafe8ebf -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:0b743438ef04fa98032f249747546bfb1d7db40a07fcf9836af4398b46b91a6a -->

Se admiten los triggers visuales enumerados y Move/Toggle/Spawn/Stop con parametros representables. Touch triggers, Move lock-Y/to-target, Rotate, Follow, Scale, area y keyframes siguen sin implementacion fiel. Un objeto desconocido rechaza la prediccion del nivel completo; los movimientos y clics del juego permanecen directos. Una rama futura no representable no deja bloqueado el intento real. Si esa mecanica afecta el estado real, el modelo deja de corregir hasta reiniciar.

<!-- /coderabbit-ai-generated:v1 --> El cargador limita posiciones y bordes a 10000000 unidades, el nivel a 250000 objetos y el indice a 200000 entradas de buckets; rechaza geometria no finita antes de reservar ese indice.

<!-- /coderabbit-ai-generated:v1 -->
- La reconstruccion debe coincidir desde el estado inicial; no inventa un estado incompleto copiando solo posicion y velocidad. Si faltan mas de 64 ticks de historial o el modelo diverge, se suspende hasta el siguiente intento.
- Se anticipa la posible accion cuatro ticks. Un clic para el que no haya una respuesta exacta disponible no recibe correccion. Esto limita la cobertura, especialmente si la consola esta ocupada.
- `normal-ticks` y `wave-ticks` limitan tanto el retraso buscado como el horizonte de supervivencia comprobado tras cada accion. Sobrevivir ese horizonte no demuestra que el resto del nivel sea seguro.
- `invisible-trajectory` apagado conserva el contrato documentado del original: entrada directa. No se dibujan trayectorias.
- Noclip y velocidad se aplican solo en practica. La correccion se suspende con noclip. El contador de noclip cuenta llamadas de colision suprimidas; un contacto continuo puede sumar varias.
- JSON de referencia: `inputs` con `frame`, `down`, opcional `button`, `2p`/`player2` y `framerate` global (240 por defecto). TXT/CSV: una linea `frame down|up|press|release|1|0` a 240 Hz. Solo se compara el boton 1 del jugador 1, misma accion, dentro de 80 ticks. `referenceDelta` se guarda en el registro; no hay reproduccion ni ajuste automatico de limites.
- No incluye la pagina Estilo ni recomendaciones automaticas del menu original. El color, imagen, opacidad, escala, arrastre del titulo, cierre, idioma y HUD se controlan desde el panel y los ajustes de Geode. Los textos de diagnostico del simulador estan en espanol.

## Comprobaciones disponibles

En Linux, sin Geode ni Geometry Dash:

```sh
cmake -S . -B build-native -DCMAKE_BUILD_TYPE=Release -DIAX_BUILD_MOD=OFF
cmake --build build-native --parallel 2
ctest --test-dir build-native --output-on-failure
GDGEN_SIM_LIB="$PWD/build-native/libgdsim.so" IAX_GATE_TEST="$PWD/build-native/iax_gate_tests" python -m unittest discover -s tests -v
```

La suite comprueba formato binario entre C++ y Python, respuestas antiguas, cambios de intento/estado, perdida de historial, plazo agotado, acciones directas seguras, una correccion con el simulador real y comunicacion UDP entre procesos. Los resultados sinteticos no prueban el comportamiento de los hooks dentro de GD.

## Compilar en Windows

Necesitas Visual Studio 2022 actualizado (MSVC >=19.44 y Windows SDK), CMake >=3.25, Geode CLI, SDK **5.11.2** con sus binarios instalados y Python **3.12**. Define `GEODE_SDK` segun la instalacion oficial de Geode. No uses el SDK 6 del otro proyecto del repositorio.

Desde PowerShell:

```powershell
./scripts/build-windows.ps1
```

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:3b3b5e0f73be788de585dd63d0a80027cab8d19c497dd74bcb8cf8cb6e384c68 -->

El script fija los bindings a `6f163558a5e2ac47b9121c6721fd32322c8e188b`, compila el puente y la DLL del simulador, ejecuta las pruebas y descarga el Python embebible oficial 3.12.10. Deja `build-windows/InputAlignExternal-windows.zip`, sin dependencias de pip. `scripts/package-windows.py` tambien permite empaquetar un directorio ya compilado con el ZIP oficial descargado previamente.

<!-- /coderabbit-ai-generated:v1 -->

```sh
python scripts/package-windows.py --build build-windows --python-runtime python-3.12.10-embed-amd64.zip --output InputAlignExternal-windows.zip
```

## Opciones conservadas

| Clave | Valor inicial |
|---|---|
| `enabled` | True |
| `invisible-trajectory` | True |
| `cbf-sync` | True |
| `language` | Español |
| `normal-ticks` | 400 |
| `wave-ticks` | 400 |
| `spam-guard` | False |
| `spam-interval` | 20 |
| `buffer-normal` | True |
| `buffer-wave` | True |
| `buffer-practice-only` | False |
| `macro-record` | True |
| `macro-file` |  |
| `macro-compare` | True |
| `background-image` |  |
| `background-opacity` | 100 |
| `background-dim` | 30 |
| `noclip` | False |
| `game-speed` | 1.0 |
| `auto-close` | 15 |
| `menu-color` | #1D1813 |
| `menu-opacity` | 90 |
| `menu-scale` | 85 |
| `menu-lock` | False |
| `hud-fps` | False |
| `hud-cps` | False |
| `hud-clicks` | False |
| `hud-saved` | False |
| `hud-noclip-deaths` | False |
| `hud-scale` | 70 |
| `hud-opacity` | 80 |
| `hud-corner` | Arriba izq. |
| `no-wave-trail` | False |
| `performance-mode` | False |
| `max-correction-ms` | 6 |
| `button-corner` | Abajo der. |
| `button-scale` | 0.7 |
| `button-opacity` | 100 |

## Procedencia y licencias

Puente, protocolo y predictor: MIT, copyright 2026 dadjdjxjfjdjd-sketch. Simulador independiente: [kholkink/gd-levelgen](https://github.com/kholkink/gd-levelgen/tree/9496709eadd22fc3a130f89043169c17da4d5b9c), MIT, revision `9496709eadd22fc3a130f89043169c17da4d5b9c`; <!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:567d2a75d4dd5dcccecb2a194f6268025c666d04ba892ce4793535a03344e8bc -->

se incluyen su licencia y el registro del fork en `worker/vendor/UPSTREAM.json`, con hashes originales y modificados. La version 0.2 aplica correcciones locales comprobables al motor de triggers y a la propiedad de estados; ya no se presenta como una copia sin cambios.

<!-- /coderabbit-ai-generated:v1 --> El autor original atribuye el simulador a GD 2.2081 y documenta limitaciones; esa atribucion no equivale a validacion de este mod en el juego.

El paquete de consola incluye Python bajo su licencia, conservada en `InputAlignWorker/LICENSE.txt`. `build-provenance.json` identifica procedencia, hashes y el estado de prueba del paquete. <!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:b448fcb9cbf457ae39807be14987c6a4ba513f2ed04d4caf8dabdc93fe004335 -->

No se redistribuyen Geometry Dash ni sus recursos.

### Licencia del puente

MIT License

Copyright (c) 2026 dadjdjxjfjdjd-sketch

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


<!-- /coderabbit-ai-generated:v1 -->


<!-- /coderabbit-ai-generated:v1 -->