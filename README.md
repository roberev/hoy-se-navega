# ¿Hoy se navega?

Wing foil en la costa de Cádiz. Responde a una sola pregunta, la que uno se
hace antes de cargar el coche:

> **¿Hoy se navega, en qué spot, a qué hora y con qué ala?**

Windguru y Windy dan viento, marea y ola por separado y te dejan a ti la
traducción. Esto hace la traducción: cruza las tres cosas contra las
particularidades de **cada spot** y contra **tu peso**, y da un veredicto con
su porqué.

---

## Lo que hay que entender antes de tocar nada

**El valor de este proyecto no está en el código. Está en
[`config/spots.yaml`](config/spots.yaml).**

Los datos meteorológicos son una commodity: gratis, públicos y los tiene
cualquiera. Lo que no tiene ninguna API es a qué altura de marea empiezas a
comerte los corrales de Chipiona, si el Poniente entra limpio o racheado por el
pueblo, o dónde aparcas en agosto. Ese fichero es el activo. El resto del
repositorio existe para servirlo.

Por eso el sistema está construido con una regla incómoda a propósito:

> **Un spot con datos locales sin rellenar nunca dice «Sí». Como mucho dice
> «Justo», y enseña en la interfaz qué le falta.**

No es un fallo, es el diseño. Prefiere quedarse corto antes que mandarte al
agua con una afirmación que nadie ha comprobado. Y hace visible el trabajo
pendiente en vez de esconderlo.

---

## Estado actual

Los 8 spots están sembrados con lo verificable (coordenadas, estación de marea
oficial, avisos de seguridad con figura legal de protección). Los campos que
requieren conocimiento local están marcados `PENDIENTE_ROBE`.

Mientras sigan así, **todos los veredictos tienen techo en «Justo»**. En cuanto
se rellene la ventana de marea y el límite de ola de un spot, ese spot empieza
a dar «Sí».

Empieza por Chipiona: son dos campos y cambian el producto entero.

---

## Arquitectura

```
GitHub Actions (cron, 4×/día)
        │
        ├─ pytest                    → si la lógica está rota, no se publica
        ├─ verify_apis.py            → si las APIs cambiaron, no se publica
        │
        ├─ build_data.py
        │     ├─ Open-Meteo Forecast   viento, racha, dirección
        │     ├─ Open-Meteo Marine     oleaje
        │     ├─ IHM                   mareas oficiales (extremos)
        │     ├─ config/spots.yaml     la capa local
        │     └─ config/alas.yaml      viento × peso → ala
        │
        └─ site/data.json  ──►  GitHub Pages (HTML estático, sin backend)
```

Sin servidor, sin base de datos, sin cuentas de usuario. **Coste: 0 €.**
GitHub Actions y Pages son gratis para repositorios públicos.

### Decisiones tomadas y por qué

**Python + stdlib para el backend, cero framework.** Las únicas dependencias
son PyYAML (para que el fichero de spots se pueda editar a mano con
comentarios) y pytest. Nada más. Menos dependencias, menos mantenimiento.

**HTML/CSS/JS a pelo en un solo fichero para el frontend.** Sin React, sin
build step, sin bundler. Una petición al HTML y otra al JSON: carga en menos
de un segundo con 3G. Un framework aquí sólo añadiría peso y una cadena de
actualizaciones que vigilar.

**El sitio no llama nunca a las APIs.** El cron las llama, calcula y escribe
un JSON estático. Las visitas leen ese fichero. Así el consumo de API no
depende del tráfico y no hay forma de superar los límites de uso.

**La marea sale del IHM, no de Open-Meteo.** Ver
[`docs/verificacion-apis.md`](docs/verificacion-apis.md) para la comparación
de las tres opciones. Resumen: Chipiona tiene estación de predicción oficial
propia; la alternativa de Open-Meteo tiene una malla de 8 km y otro datum.

**El ala se recalcula en el navegador.** El JSON lleva la tabla de
`alas.yaml` y el viento de la franja; el JavaScript aplica el peso guardado.
Así el peso es instantáneo y personal sin necesidad de servidor ni de generar
un JSON por cada peso posible.

**Si el cron falla, no se borra nada.** Si un spot no se puede actualizar se
conservan sus últimos datos válidos marcados como obsoletos, con aviso visible
y la fecha de la última actualización buena. Si falla todo, no se publica: el
despliegue anterior sigue en pie. Datos viejos presentados como frescos son
peor que no tener sitio.

---

## Cómo funciona el veredicto

Tres condiciones independientes. **Gana la más restrictiva.**

1. **Viento** — dentro del rango navegable, dirección válida para el spot, y
   sin rachas desproporcionadas (racha/media por encima de 1,6 → fuera).
2. **Marea** — dentro de la ventana del spot. Como el IHM sólo da extremos, la
   altura a cada hora se interpola con una curva semi-cosenoidal.
3. **Mar** — ola por debajo del umbral del spot.

Cada condición devuelve su estado **y su motivo**. El motivo viaja hasta la
interfaz: por eso el sitio no dice "No", dice *"No: marea baja, 0.9 m (hacen
falta 1.8)"*.

Además cada condición lleva una marca de **confianza**. Si el dato local no
existe todavía, la condición no bloquea horas concretas (eso ensancharía la
franja hasta hacerla inútil) pero impide que el día llegue a «Sí».

**Fiabilidad:** hoy y mañana `alta`, dos y tres días `media`, cuatro y cinco
`baja`. Se muestra siempre. Una previsión a cinco días no vale lo que la de
mañana y el producto no debe fingir que sí.

---

## Puesta en marcha

```bash
git clone <tu-repo> && cd hoy-se-navega
pip install -r requirements-dev.txt

python -m pytest -q                 # 71 tests de la lógica, sin red
python scripts/verify_apis.py       # comprueba las APIs reales
python scripts/build_data.py        # genera site/data.json

cd site && python -m http.server 8000
```

### Desplegar en GitHub Pages

1. Crea el repositorio en GitHub y sube esto (público, para que Actions y
   Pages sean gratis).
2. **Settings → Pages → Source: GitHub Actions.**
3. **Actions → "Actualizar previsión y publicar" → Run workflow** para la
   primera ejecución.

A partir de ahí se actualiza solo a las 06:20, 10:20, 14:20 y 19:20 (hora
peninsular de verano), y cada vez que toques `config/spots.yaml`.

> Nota: GitHub desactiva los cron de un repositorio sin actividad durante 60
> días. Un commit de vez en cuando, o entrar a darle a "Run workflow", lo
> reactiva.

### Dominio propio

Settings → Pages → Custom domain, un registro `CNAME` apuntando a
`<usuario>.github.io` y un fichero `site/CNAME` con el dominio. Sin coste más
allá del dominio.

---

## Cómo calibrar un spot

Abre `config/spots.yaml`, busca el bloque y sustituye los `PENDIENTE_ROBE`.
Los dos que más cambian el resultado:

```yaml
    marea:
      ventana:
        tipo: altura_minima
        altura_min_m: 1.8        # por debajo de esto no se navega aquí

    mar:
      ola_max_m: 1.2             # por encima, fuera
```

También existe `tipo: horas_alrededor` si te resulta más natural pensar en
"tres horas antes y tres después de la pleamar":

```yaml
      ventana:
        tipo: horas_alrededor
        referencia: pleamar
        horas_antes: 3
        horas_despues: 3
```

Haz commit y el sitio se republica solo.

### Añadir un spot

Copia un bloque entero, cambia `id`, `nombre`, `coordenadas` y la
`estacion_ihm`. Las estaciones disponibles de Conil a Algeciras están listadas
en [`docs/verificacion-apis.md`](docs/verificacion-apis.md). **No hay que tocar
código.**

### Ajustar la tabla de alas

`config/alas.yaml`. La tabla está escrita para 75 kg; el escalado por peso
(±10 kg ≈ ±0,5 m²) está marcado como suposición a calibrar con uso real.

---

## Licencias — leer antes de monetizar

Las dos fuentes son de **uso no comercial**:

- **Open-Meteo**: CC-BY 4.0, tier gratuito no comercial. Clasifica
  explícitamente como comerciales las webs *con suscripción o publicidad*.
- **IHM**: RD 1495/2011, *"no se autoriza el uso comercial de ninguna
  información contenida en este geoportal ni en ninguno de sus servicios"*.

**Meter patrocinio de tiendas o escuelas incumpliría ambas.** Es una decisión
consciente aplazada, no un descuido: hoy el proyecto es personal y sin ánimo
de lucro, que es donde encajan las licencias.

El día que haya que monetizar, el acceso a datos está aislado en
`scripts/lib/sources.py`. Cambiar de fuente es reescribir ese fichero, no el
proyecto. Las alternativas y su coste están anotadas en
[`IDEAS.md`](IDEAS.md).

---

## Aviso

Esto es una **ayuda a la decisión, no una garantía**. Los modelos fallan, la
mar cambia y ningún dato sustituye a mirar el agua. La responsabilidad de
entrar es del rider. El aviso está permanentemente visible en el sitio.

---

## Estructura

```
config/spots.yaml           el activo: la capa local, editable a mano
config/alas.yaml            viento × peso → ala
scripts/build_data.py       orquesta: APIs → veredictos → JSON
scripts/verify_apis.py      verificación viva de las fuentes
scripts/lib/sources.py      acceso HTTP, caché y reintentos
scripts/lib/tides.py        extremos del IHM → curva horaria
scripts/lib/verdict.py      las tres condiciones y la regla del más restrictivo
scripts/lib/day.py          horas → veredicto del día, franja y porqué
scripts/lib/wings.py        tabla de alas y escalado por peso
site/index.html             el sitio entero, un fichero
tests/                      71 tests, sin red
docs/verificacion-apis.md   qué devuelve cada fuente y qué no
IDEAS.md                    lo descartado, para no perderlo
```
