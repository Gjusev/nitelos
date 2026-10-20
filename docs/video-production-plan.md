# Nitelos — plan de producción audiovisual para Claude Opus 5.5

## 1. Encargo y resultado esperado

Crear un paquete de presentación y documentación que presente Nitelos a desarrolladores de agentes: un vídeo corto con motion graphics dinámicos, una demo técnica, recursos visuales reutilizables y una mejora integral del README y las guías. Este documento es el plan de ejecución; no acredita que los vídeos, las capturas o las mejoras documentales ya existan.

Concepto creativo: **«Del intento a la evidencia»**. Una afirmación de éxito se convierte visualmente en una pregunta; el criterio y la evidencia permiten emitir un resultado. La animación debe explicar ese recorrido.

Mensaje de marca existente: **Verify the outcome, not the attempt.**

Supuestos editables, sin bloquear el arranque:

- Público: desarrolladores de agentes, herramientas de automatización y equipos de infraestructura de IA.
- Idioma de las piezas: español; conservar el tagline de marca y los identificadores del SDK en inglés. Centralizar el copy para facilitar una futura versión inglesa.
- Distribución prevista: README, página de proyecto, redes y presentación técnica.
- Estilo: motion editorial técnico, tipografía protagonista, diagramas animados y evidencia real de ejecución.
- Sin locución en la versión inicial; debe entenderse con el sonido apagado. Música y efectos, si hay material con licencia disponible.
- No publicar ni subir contenido a servicios externos como parte de la producción local.

## 2. Investigar antes de producir

Leer las instrucciones del repositorio y consultar:

1. `README.md`, `pyproject.toml`, `docs/quickstart.md`.
2. `examples/demo_incomplete_form.py`, `examples/demo_external_pending.py`, `examples/quickstart.py`.
3. `docs/success-criteria.md`, `docs/evidence-limits.md`, `docs/errors-and-abstention.md`.
4. `src/nitelos/` para resolver dudas sobre contratos y campos.
5. Marca, logos, fuentes y recursos existentes, si aparecen durante el inventario.

El proyecto contiene un SDK Python, ejemplos y documentación. No asumir que existe una aplicación web. Cualquier panel dibujado para el vídeo será una **visualización explicativa**, no una captura de una interfaz comercial existente.

Hay señales de documentación desfasada: `docs/planning/README.md` habla de implementación no iniciada, aunque existen fuentes; el README dice que no se han ejecutado evaluaciones, aunque existen archivos en `reports/`. Resolver las afirmaciones contra código y ejecución actual. No usar cifras de rendimiento o precisión en estas piezas: la presencia de informes no basta para aprobar un claim comercial.

### Reglas de fidelidad

- Nitelos evalúa criterios frente a evidencia suministrada por el host. No navega, hace clic, recoge por sí solo evidencia externa ni reintenta tareas.
- `success`, `failure` y `abstained` son decisiones relativas a esos criterios y esa evidencia, en un checkpoint; no garantías generales sobre el mundo.
- Separar `execution_status` de `decision`: una verificación puede ejecutarse correctamente y concluir `failure`.
- «Sin evidencia suficiente» debe conducir visualmente a abstención, no a éxito ni automáticamente a fallo.
- No confundir los estados de criterio `supported/refuted/unknown` con la decisión agregada.
- La inferencia visual es opcional y experimental. Excluirla de la demo principal para mantener una historia determinista y reproducible.
- No inventar clientes, integraciones, benchmarks, porcentajes, latencias ni enlaces públicos.
- Las fixtures son sintéticas; sus fechas no acreditan eventos reales. Indicar «Ejemplo sintético» en la demo.

## 3. Entregables

| Pieza | Duración / formato | Contenido y finalidad |
|---|---|---|
| Vídeo principal | 30 s, 1920×1080, 30 fps | Problema, evidencia, resultado y cierre de marca |
| Adaptación vertical | 30 s, 1080×1920, 30 fps | Misma historia con composición específica para móvil |
| Demo técnica | 60 s, 1920×1080, 30 fps | Ejecución real de los tres ejemplos y explicación legible |
| Teaser | 8 s, 1080×1920, 30 fps | Claim, contradicción visual y marca |
| Loop de producto | 6 s, 1600×900, sin audio | Criterio → evidencia → decisión; MP4 y WebM |
| Kit estático | SVG y PNG | Wordmark tipográfico, diagrama, tres tarjetas de estado |
| Imágenes de difusión | PNG | Portada 1920×1080, tarjeta social 1200×630 y póster vertical 1080×1920 |
| Handoff | Fuentes y documentación | Timeline editable, assets, licencias, comandos, pruebas y manifiesto |

MP4 de entrega: H.264, píxel `yuv420p`, audio AAC cuando corresponda y fast-start. Mantener textos editables y recursos vectoriales. No prometer transparencia en H.264.

Prioridad: completar y validar primero el vídeo principal horizontal; después la demo; después adaptaciones y recursos. No pulir todas las variantes antes de comprobar que funciona la historia central.

## 4. Dirección artística

### Sistema visual propuesto

Si no existe identidad visual, usar esta propuesta como identidad audiovisual provisional:

- Fondo carbón `#101318`, texto marfil `#F4F1E9`, líneas secundarias `#59616F`.
- Evidencia: azul claro `#79BFFF`. Resultado respaldado: verde `#95D8AC`. Refutación: coral `#FF877A`. Abstención: ámbar `#F0C878`.
- Combinar cada color con palabra e icono; el significado no depende solo del color.
- Tipografía sans de buena legibilidad y monoespaciada para código, con licencia verificable y archivos locales. Reutilizar las fuentes existentes si las hay.
- Wordmark «nitelos» sencillo. No presentar un símbolo nuevo como logo oficial aprobado.
- Composición con espacio negativo, una idea dominante por plano y máximo dos niveles secundarios.
- Evitar lluvia de código, robots genéricos, partículas sin significado, interfaces llenas de números inventados y zooms constantes.

### Recursos visuales concretos

1. **Tarjeta de afirmación:** «Registro completado». Lleva etiqueta «Agente»; no se confunde con el veredicto.
2. **Recorte de evidencia:** `validation_error: true`, ampliado con resaltado preciso.
3. **Regla de comprobación:** esperado `false` frente a observado `true`.
4. **Conector de evidencia:** línea que une criterio, observación y resultado.
5. **Tres estados:** `success`, `failure`, `abstained`, cada uno con texto explicativo breve.
6. **Terminal real:** salida capturada de los ejemplos, encuadrada y ampliada.
7. **Diagrama del host y SDK:** el host suministra evidencia; Nitelos evalúa y devuelve el resultado.
8. **Cierre tipográfico:** wordmark, tagline y CTA «Explora el SDK». Añadir URL solo si se verifica en el repositorio.

### Gramática de movimiento

- Movimiento principal: la tarjeta de afirmación se desplaza y deja descubrir la evidencia que estaba detrás.
- Transición distintiva: el subrayado de `/validation_error` se extiende hasta convertirse en el conector del diagrama.
- Usar continuidad de objetos entre planos, máscaras de texto, trazado SVG y cambios de escala medidos.
- Entradas de 250–450 ms, desfases de 50–90 ms y pausas de lectura de al menos 1,5–2 s para mensajes clave.
- El ritmo puede acelerar en transiciones; los datos y el código permanecen quietos mientras se leen.
- Máximo dos elementos compitiendo por atención. Evitar destellos y rebotes decorativos en veredictos.
- En 1080p: titulares de 72–100 px, texto principal de 36–48 px y código destacado de al menos 28 px. Comprobar legibilidad en reproducción reducida.
- Vertical: recomponer en columna; margen lateral mínimo del 8 %, reserva superior del 10 % e inferior del 18 % para interfaces sociales. No recortar mecánicamente el horizontal.

## 5. Storyboard del vídeo principal — 30 segundos

| Tiempo | Texto visible | Visual y movimiento | Evidencia / función |
|---|---|---|---|
| 0–3 s | «El agente dice: completado.» | Tarjeta entra con decisión; énfasis tipográfico en «completado» | Afirmación del agente, etiquetada como tal |
| 3–6 s | «¿Qué demuestra la evidencia?» | Tarjeta se desplaza; aparece `validation_error: true` | Dato del ejemplo de formulario |
| 6–10 s | «Define el criterio.» | Se dibuja la regla: «Sin errores de validación»; esperado `false` | Enseñar qué se comprueba |
| 10–15 s | «Contrástalo con la evidencia.» | Comparación `false` / `true`; subrayado se transforma en conector | Visualización explicativa basada en fixture |
| 15–19 s | `decision: failure` | Resultado coral, transición limpia; debajo «El criterio queda refutado» | No confundir fallo del criterio con error de ejecución |
| 19–23 s | «Sin evidencia suficiente: abstained.» | Breve segundo caso: herramienta «completed», evidencia externa ausente, estado ámbar | Caso externo pendiente; no es la continuación del formulario |
| 23–27 s | «Criterio. Evidencia. Decisión.» | Se ordenan tres nodos y aparece Nitelos como verificador | Mostrar el papel del SDK |
| 27–30 s | «nitelos» / «Verify the outcome, not the attempt.» | Cierre quieto con «Explora el SDK» | Lectura clara, sin URL inventada |

La pieza principal comunica el problema y la propuesta. La demo amplía la integración y enseña también el caso de éxito.

## 6. Demo técnica — 60 segundos

### Secuencia

| Tiempo | Acción y contenido |
|---|---|
| 0–5 s | «Tres resultados. Evidencia explícita.» Presentación del SDK; etiqueta «Ejemplos sintéticos · ejecución local» |
| 5–13 s | Diagrama del host: criterio + observación normalizada → `Verifier().verify(request)` |
| 13–29 s | Ejecutar `demo_incomplete_form.py`; ampliar `validation_error`, el valor esperado y la salida real `failure`; enseñar la referencia de evidencia que realmente emita |
| 29–41 s | Ejecutar `quickstart.py`; mostrar criterio satisfecho y salida real `success` |
| 41–53 s | Ejecutar `demo_external_pending.py`; mostrar ausencia de evidencia externa y salida real `abstained` |
| 53–60 s | Tabla de tres decisiones y cierre: «Verificación de criterios basada en evidencia» |

### Captura reproducible

1. Registrar commit, versión de Python, comando, código de salida y stdout/stderr de cada ejecución.
2. Preferir el entorno existente; no actualizar dependencias del SDK para hacer el vídeo.
3. En PowerShell, si el entorno local está disponible:

   ```powershell
   & .\.venv\Scripts\python.exe examples/demo_incomplete_form.py
   & .\.venv\Scripts\python.exe examples/quickstart.py
   & .\.venv\Scripts\python.exe examples/demo_external_pending.py
   ```

4. Si falta ese entorno, seguir `docs/installation.md` en un entorno aislado, conservando el lockfile del proyecto.
5. Guardar la salida literal; derivar de ella cualquier terminal estilizado. Identificar este último como «Salida real · visualización editada» si no se usa una grabación directa.
6. Los veredictos anteriores son expectativas obtenidas de las fuentes, no resultados ejecutados durante la redacción de este plan. Si difieren, investigar y actualizar el guion; nunca editar el stdout para que encaje.
7. No mostrar tiempos acelerados como medida de rendimiento. Omitir tiempos de ejecución en la pieza.
8. Un recorte de código puede omitir la construcción de `request`, pero debe indicar «request preparado con criterios y evidencia»; no presentarlo como ejemplo completo ejecutable.

## 7. Producción técnica

Crear un proyecto audiovisual separado en `videos/nitelos-launch/`. Mantener intactas las dependencias y fuentes del SDK.

Ruta preferida: HyperFrames con HTML/CSS/SVG y timeline determinista. Antes de implementar, leer las skills disponibles `hyperframes`, `hyperframes-core`, `hyperframes-animation` y `hyperframes-cli`. Usar el flujo de vídeo general o de producto adecuado para las piezas de 30/60 s; reservar `motion-graphics` para el teaser y elementos breves.

Este entorno es Windows. Las instrucciones locales de motion graphics consultadas enumeran macOS/Linux como prerrequisitos: **no dar por comprobada la compatibilidad con Windows**. Confirmar herramientas y documentación oficial vigente al ejecutar. Hacer una prueba de render de 2 s antes de construir toda la timeline.

Si HyperFrames no funciona en el entorno disponible, documentar el error y usar un entorno Linux/WSL ya disponible y compatible, o una composición HTML/SVG con captura determinista de frames mediante Playwright y codificación con FFmpeg. No instalar un sistema operativo como paso implícito. El fallback también debe superar la prueba de 2 s con fuentes, transparencia interna y audio comprobados.

No fijar versiones ni copiar flags de memoria: consultar la ayuda y la documentación oficial de las versiones instaladas. Guardar versiones y lockfile en el proyecto audiovisual. No depender de red, fuentes remotas ni aleatoriedad sin semilla durante el render.

### Organización propuesta

```text
videos/nitelos-launch/
  BRIEF.md
  README.md
  claims.md
  storyboard.md
  copy.es.json
  tokens.json
  compositions/
  assets/
    fonts/
    audio/
    svg/
    licenses.md
  evidence/
    commands.md
    incomplete-form.stdout.txt
    quickstart.stdout.txt
    external-pending.stdout.txt
  proofs/
    contact-sheet.png
    qa.md
  renders/
  stills/
  manifest.json
```

`claims.md` relaciona cada afirmación del vídeo con archivo fuente, ejecución o decisión editorial. `manifest.json` registra por entregable ruta, dimensiones, duración, fps, codecs, presencia de audio y comando de render.

### Audio

- Base instrumental discreta, propuesta de 110–120 BPM; ajustar cortes al ritmo sin sacrificar lectura.
- Efectos breves para aparición de evidencia, conexión y veredicto; no sonorizar cada letra.
- Usar assets locales con licencia documentada. Si no hay música autorizada, entregar versión silenciosa completa y registrar la omisión.
- Como objetivo de mezcla, aproximadamente −16 LUFS integrados y pico verdadero máximo de −1 dBTP; medir, no asumir.
- No activar servicios de pago ni consumir créditos sin autorización existente.

## 8. Ejecución por fases y criterios de salida

| Fase | Trabajo | Criterio para avanzar |
|---|---|---|
| A. Evidencia | Inventario, lectura, ejecución de tres ejemplos y mapa de claims | Salidas reales guardadas; diferencias resueltas o explícitamente bloqueadas |
| B. Diseño | Brief, tokens, copy, storyboard y tres keyframes: apertura, evidencia, cierre | Composición legible y consistente; ninguna UI ficticia presentada como real |
| C. Viabilidad | Proyecto aislado y render de prueba de 2 s | Archivo reproducible con dimensiones, fuentes y codec correctos |
| D. Animatic | Montaje completo del principal con tiempos y texto definitivos | 30 s de historia comprensible sin audio; revisar lectura a tamaño móvil |
| E. Acabado | Movimiento, diagramas, terminal, música y efectos disponibles | Inspección de frames y reproducción completa sin errores |
| F. Demo | Montar 60 s desde evidencia ejecutada | Tres casos distinguibles y semántica de decisiones correcta |
| G. Adaptación | Vertical, teaser, loop, estáticos | Reencuadres específicos; loop sin salto; recursos coherentes |
| H. Entrega | Exportar, medir, documentar y comprobar todos los archivos | Manifiesto completo y comandos reproducibles |

Si se aplican skills con un paso explícito de aprobación de render, respetarlo cuando no exista autorización previa para renderizar. Preparar antes el preview completo y las pruebas; formular una sola petición concreta con el enlace a la skill que exige ese paso. Este plan por sí solo no constituye una orden de ejecución, publicación ni compra.

## 9. Control de calidad

- Inspeccionar capturas a 1, 4, 8, 12, 17, 21, 25 y 28,5 s del vídeo principal, además de los límites de cada transición.
- Reproducir cada vídeo entero: los fotogramas aislados no detectan tirones, cortes de audio ni duraciones de lectura deficientes.
- Verificar que el primer frame y el cierre están compuestos intencionalmente, sin negro accidental ni fuentes pendientes de carga.
- No hay textos cortados, referencias a evidencia inventadas ni resultados que discrepen del stdout.
- Comprobar contraste, legibilidad al 50 % y en móvil, márgenes y ausencia de parpadeos.
- Revisar el empalme del loop repitiéndolo tres veces.
- Verificar con FFprobe o equivalente las dimensiones, fps, duración y codecs; tolerancia de duración de un frame.
- Validar audio mediante medición si se incluye; revisar inicio y final para evitar clics.
- Todas las fuentes, iconos y pistas tienen procedencia y licencia registradas.
- Entregar archivos finales reales y no vacíos, fuentes editables y lista explícita de cualquier limitación. No describir una previsualización como MP4 renderizado.

## 10. README y documentación del proyecto

Este trabajo es parte del encargo, no una sugerencia posterior. Ejecutarlo junto con la producción audiovisual: primero corregir los hechos y la experiencia de inicio; después integrar los recursos que se hayan generado. Mantener la documentación pública en inglés, coherente con el repositorio actual; el copy audiovisual continúa en español. No duplicar toda la documentación en dos idiomas.

### README: recorrido recomendado

Reescribir `README.md` para que un desarrollador pueda entender el producto, ejecutar un ejemplo y encontrar sus límites sin recorrer el plan de implementación.

1. **Presentación:** nombre, tagline existente y una frase concreta que explique el SDK y su público. Evitar promesas de éxito universal.
2. **Demostración visual:** portada ligera que enlace a la demo real, con texto alternativo. Incorporarla solo cuando el archivo exista; el README debe seguir funcionando sin reproducir vídeo.
3. **Problema y ejemplo:** afirmación de registro completado frente a `validation_error: true`, con resultado `failure` y enlace al ejemplo ejecutable.
4. **Cómo funciona:** diagrama breve de host → criterios y evidencia → Nitelos → resultado. Mostrar explícitamente que la evidencia la suministra el host.
5. **Inicio rápido:** requisitos, instalación comprobable, ejemplo mínimo completo y salida real. No usar variables sin definir ni omitir el hash necesario para que el ejemplo funcione.
6. **Interpretación del resultado:** tabla de `success`, `failure`, `abstained` y explicación separada de errores de ejecución y `decision: None`.
7. **Capacidades y límites:** núcleo determinista, confianza externa y backend visual experimental; distinguir funcionalidad implementada, validada y futura.
8. **Evaluación:** resumen prudente del estado comprobado con enlace a metodología e informes. No convertir resultados sintéticos en afirmaciones de precisión general.
9. **Navegación:** enlaces por tarea: instalar, integrar, interpretar resultados, evaluar y contribuir.
10. **Contribución, seguridad y licencia:** enlaces existentes, sin duplicar sus políticas.

Conservar detalles contractuales importantes en las guías enlazadas. Usar badges solo cuando apunten a CI, versiones o licencias verificables. No añadir botones ficticios, estrellas simuladas ni adornos que dificulten la lectura.

### Alcance por archivo

| Archivo | Mejora requerida | Evidencia de finalización |
|---|---|---|
| `README.md` | Reorganizar según el recorrido anterior e integrar demo y diagrama | Un lector puede ejecutar el primer ejemplo y explicar las tres decisiones |
| `docs/README.md` (nuevo si no existe) | Índice por tareas, con ruta inicial y separación entre guías públicas y planificación histórica | Todos los documentos públicos relevantes tienen una entrada y enlaces válidos |
| `docs/installation.md` | Diferenciar instalación desde checkout y desde paquete publicado; core, eval y visual; requisitos y plataformas | Comandos contrastados con configuración real y al menos instalación local validada |
| `docs/quickstart.md` | Ejemplo completo reproducible, salida literal y siguiente paso de integración | Snippet ejecutado desde un entorno adecuado, sin variables implícitas |
| `docs/success-criteria.md` | Explicar alcance, checkpoint, estados de criterio y decisión agregada con ejemplos | Coincide con contratos y salidas reales |
| `docs/errors-and-abstention.md` | Tabla de situaciones, resultado y acción del integrador; distinguir error, refutación y abstención | Nombres y códigos extraídos del SDK, no inventados |
| `docs/backends.md` | Revisar estado del backend visual, checkpoint y plataforma realmente probados | Coincide con configuración e informes; límites visibles |
| `docs/evaluation.md` | Corregir afirmaciones desfasadas sobre ejecuciones; enlazar informes con alcance y limitaciones | Cada cifra publicada tiene fuente, split, denominador y contexto |
| `docs/traces.md` y `docs/recipes/caller-collection.md` | Aclarar quién recoge y normaliza evidencia; ejemplo de integración con host | No atribuye navegación, capturas o reintentos autónomos al SDK |
| `docs/evidence-limits.md` y `docs/security-privacy.md` | Revisar coherencia de límites, confianza y datos sintéticos | Sin contradicciones con README o demo |
| `CONTRIBUTING.md` | Revisar setup y comandos reales de desarrollo; corregir ambigüedades | Comandos vigentes; distinguir DCO sign-off de firma criptográfica |
| `docs/planning/README.md` | Identificar la baseline como planificación histórica y enlazar estado actual | No afirma que el repositorio actual carece de implementación |

Auditar también las demás guías públicas y corregir enlaces, terminología y afirmaciones obsoletas cuando haya evidencia concreta. No reescribir contratos normativos ni ADR históricos para hacerlos coincidir artificialmente con el marketing; añadir contexto de estado y enlaces de sucesión cuando corresponda.

### Verificación de afirmaciones y comandos

- Revisar `reports/v0.1/SUMMARY.md`, `run.json`, `metrics.json` y casos subyacentes antes de afirmar que una evaluación se completó. Comprobar coherencia entre resumen e informes; registrar discrepancias sin alterar los resultados.
- El README actual afirma que no se han ejecutado evaluaciones y el índice de planificación describe ausencia de implementación. Son puntos de auditoría prioritarios, no texto que deba conservarse por inercia.
- La publicación en PyPI no se deduce de `pyproject.toml`. Verificarla en la fuente oficial antes de recomendar `pip install nitelos` como ruta disponible. Si no se puede confirmar, priorizar instalación desde el checkout y declarar el estado de publicación sin inventarlo.
- No confundir la compatibilidad del núcleo Python con la del backend visual opcional o las herramientas de vídeo.
- Ejecutar los snippets nuevos o modificados que se presenten como completos. Guardar comando, entorno, salida y resultado de la comprobación. No volver a ejecutar benchmarks costosos para corregir redacción si los informes existentes permiten documentar el estado.
- Revisar enlaces relativos, anclas, imágenes y referencias a símbolos públicos. Comprobar la representación de tablas, código y diagramas en Markdown compatible con GitHub.
- Una modificación documental no exige tests nuevos que repitan el texto. Si se descubre un fallo de comportamiento, documentarlo y mantener separado cualquier cambio funcional del encargo audiovisual/documental.

### Integración de los recursos audiovisuales

- Guardar los assets ligeros de documentación en `docs/assets/`; conservar masters y fuentes de producción en `videos/nitelos-launch/`.
- Reutilizar el diagrama del vídeo como SVG estático accesible y una portada optimizada con enlace a la demo. El contenido esencial debe tener explicación textual.
- Objetivo de peso: portada inferior a 500 KB y kit embebido en el README inferior a 1 MB. Preferir imagen enlazada sobre GIF pesado.
- No añadir MP4 grandes al historial ni configurar Git LFS silenciosamente. Entregarlos localmente y documentar su ubicación; integrar un enlace remoto solo cuando exista un destino real autorizado.
- No enlazar archivos locales sin seguimiento como si fueran accesibles para lectores del repositorio publicado. Si el vídeo aún no tiene destino distribuible, integrar el diagrama y la portada sin enlace ficticio, y registrar ese pendiente.

### Orden y entrega documental

1. Después de la fase A, crear `docs/documentation-audit.md` con archivo, problema concreto, evidencia y corrección prevista.
2. Antes del cierre del guion, corregir las afirmaciones sobre capacidades y estado para alinear vídeo y documentación.
3. Reescribir README, instalación, quickstart e índice; continuar con las guías de la tabla.
4. Después de las fases E–G, integrar los recursos visuales disponibles.
5. Añadir a la fase H la revisión de navegación y snippets, un resumen de archivos modificados y las limitaciones pendientes. Registrar verificaciones en `docs/documentation-validation.md`, distinguiendo comprobado, fallido y no ejecutado.

La documentación se considera terminada cuando ofrece un recorrido reproducible desde instalación hasta interpretación del resultado, mantiene los límites del SDK, elimina las contradicciones detectadas y enlaza únicamente recursos reales. Un bloqueo del render no debe impedir terminar las mejoras documentales independientes.

## 11. Prompt listo para Claude Opus 5.5

```text
Trabaja en el repositorio Nitelos. Lee docs/video-production-plan.md y las
instrucciones aplicables del repositorio. Ejecuta el plan como director de motion
graphics, desarrollador de la composición audiovisual y editor técnico.

Objetivo: producir un vídeo principal de 30 s, una demo técnica de 60 s,
adaptación vertical, teaser de 8 s, loop de 6 s y kit visual, con fuentes editables.
Usa el concepto «Del intento a la evidencia» y el storyboard del documento.
También mejora README.md y la documentación siguiendo íntegramente la sección 10:
auditoría factual, inicio rápido reproducible, índice por tareas, guías coherentes
e integración de recursos visuales reales. Mantén la documentación pública en inglés.

Empieza verificando el estado real del SDK y ejecutando los tres ejemplos.
Conserva sus salidas y úsalas como fuente de los resultados mostrados. No inventes
funcionalidades, interfaces existentes, métricas, clientes ni enlaces. Mantén
la distinción entre ejecución correcta y decisión success/failure/abstained.

Trabaja en videos/nitelos-launch/ para la producción audiovisual y en README.md,
CONTRIBUTING.md y docs/ para documentación, sin cambiar el comportamiento ni las
dependencias del SDK. Usa las skills audiovisuales disponibles y comprueba
compatibilidad con Windows mediante un render de 2 s antes de producir el resto.
Consulta documentación oficial vigente cuando necesites resolver herramientas.

Toma decisiones rutinarias siguiendo los supuestos del plan. Completa las fases
en orden y corrige los defectos detectados. La producción local y los renders
finales están autorizados por esta instrucción; no publiques, compres assets ni
consumas servicios de pago. Respeta cualquier restricción superior del entorno.

Entrega las piezas reales, no solo código o storyboard. Si hay un bloqueo técnico,
documenta el error y completa los entregables independientes que sigan siendo
viables. Incluye evidencias, contact sheet, QA, licencias, manifiesto y comandos
de reproducción. Entrega también los documentos modificados, la auditoría y el
registro de validación de snippets y enlaces. Al terminar, informa de las rutas
de los archivos generados, los cambios documentales y cualquier limitación pendiente.
```
