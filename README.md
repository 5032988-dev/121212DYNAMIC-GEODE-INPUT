<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:029ffa86f4d1295769a73805d04c72994ec7958ba929a979df999afe82795950 -->

# InputAlign External

Se recuperó el proyecto completo de `InputAlignExternal-v0.3-source.zip`, incorporado por el usuario en `675c7ad08b4098d2c033ce5c4d946244b98bac0b`. Los ZIP originales se conservan intactos. El código editable y las pruebas están en `InputAlignExternal/`.

Cambios actuales: suspensión segura ante errores de replay UDP y rechazo temporal de Stop/Pause/Resume por discrepancia entre el modelo heredado y el manual del editor. Véase `InputAlignExternal/README.md`. Se conservan siete candidatos, ajustes hasta 400 y Shift+Tab; no se promete cobertura universal.

Para compilar y ejecutar la suite Linux, desde `InputAlignExternal/`:

```sh
cmake -S . -B build-native -DCMAKE_BUILD_TYPE=Release -DIAX_BUILD_MOD=OFF
cmake --build build-native --parallel 2
ctest --test-dir build-native --output-on-failure
GDGEN_SIM_LIB="$PWD/build-native/libgdsim.so" IAX_GATE_TEST="$PWD/build-native/iax_gate_tests" python3 -m unittest discover -s tests -v
```

Desde la raíz, `python3 scripts/package_worker_fix.py --output /tmp/InputAlignExternal-workerfix.zip` combina los binarios originales con los scripts reparados, actualiza la procedencia y verifica CRC/hashes. No recompila Windows. Los manifiestos SOURCE/DELIVERY originales describen el archivo importado, no las reparaciones posteriores.

El juego real, FPS, equivalencia completa de estado y funciones físicas nuevas siguen sin validar. La documentación del proyecto explica la compilación completa Windows; requiere el SDK y toolchain correspondientes.


<!-- /coderabbit-ai-generated:v1 -->