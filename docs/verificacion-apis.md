# Verificación de APIs

Qué se comprobó, qué devuelve cada fuente y qué **no** devuelve.
Fecha de la verificación: **13 de agosto de 2026**.

Esta verificación se repite automáticamente en cada ejecución del cron
(`scripts/verify_apis.py`). Si una fuente cambia, el despliegue falla en vez
de publicar datos rotos.

---

## Resumen de la decisión

| Necesidad | Fuente elegida | Por qué |
|---|---|---|
| Viento (media, racha, dirección) | Open-Meteo Forecast API | Gratis, sin clave, unidades en nudos nativas |
| Oleaje | Open-Meteo Marine API | Misma casa, mismo formato horario |
| **Marea** | **API del Instituto Hidrográfico de la Marina** | Predicción oficial, estación propia en Chipiona |

La marea era el punto de mayor riesgo del proyecto y se resolvió mejor de lo
esperado: **Chipiona tiene estación de predicción propia del IHM**, no hay que
interpolar desde Cádiz ni desde Bonanza.

---

## 1. Open-Meteo — Forecast API

**Endpoint:** `https://api.open-meteo.com/v1/forecast`

Variables horarias usadas, todas confirmadas en la documentación oficial:

- `wind_speed_10m`, `wind_gusts_10m`, `wind_direction_10m`, `temperature_2m`

Parámetros relevantes:

- `wind_speed_unit=kn` → **devuelve nudos directamente**. No se convierte nada
  a mano, que es donde se cuelan los errores de factor 1,94.
- `timezone=Europe/Madrid` → las marcas horarias vienen ya en hora local, sin
  desplazamiento de UTC que aplicar.
- `forecast_days` admite de 0 a 16. Usamos 5.

**Límites de uso (tier gratuito, no comercial):** 600 llamadas/minuto,
5.000/hora, 10.000/día.
Consumo real del proyecto: 8 spots × 2 llamadas × 4 ejecuciones al día ≈ **64
llamadas/día**. Estamos dos órdenes de magnitud por debajo del límite.

**Licencia:** CC-BY 4.0. Requiere atribución (está en el pie del sitio).
**Uso no comercial**: Open-Meteo clasifica explícitamente como comerciales las
webs *con suscripción o publicidad*. Ver la sección de licencias del README.

---

## 2. Open-Meteo — Marine API

**Endpoint:** `https://marine-api.open-meteo.com/v1/marine`

Variables usadas: `wave_height`, `wave_period`, `wave_direction`,
`swell_wave_height`, `swell_wave_period`, `swell_wave_direction`.

**Riesgo conocido:** la malla marina no cubre puntos en tierra. Si las
coordenadas de un spot caen del lado seco de la línea de costa, `wave_height`
vuelve entero a `null`. `verify_apis.py` lo comprueba explícitamente y avisa
de que hay que desplazar el punto mar adentro. El código trata la falta de
oleaje como *sin confianza*, nunca como "mar en calma".

---

## 3. Marea — las tres opciones que se compararon

### Opción A — Open-Meteo `sea_level_height_msl` · **descartada**

Existe y es gratis, pero no sirve para esto:

- Procede del modelo **SMOC de Copernicus**, malla de **0,083° (~8 km)**.
  A esa resolución la costa gaditana es prácticamente un borrón. La propia
  documentación de Open-Meteo dice que las mareas son "altamente localizadas"
  y que el dato "no es apto para navegación costera".
- Va referido al **nivel medio del mar global**, no al cero del puerto que usan
  las tablas de marea. Los números no serían comparables con lo que Robe tiene
  en la cabeza.
- Se actualiza sólo una vez al día.

No se descarta del todo: se usa como **contraste independiente de la fase**
en `verify_apis.py`, para detectar un error de zona horaria en la fuente
principal. Para eso sí vale.

### Opción B — Puertos del Estado (REDMAR / PORTUS) · **descartada**

Es la red de mareógrafos oficial y tiene estaciones en la zona. Pero el acceso
a los datos es por **widgets iframe** pensados para incrustar gráficas en una
web, no por una API con contrato documentado. No hay endpoint JSON/CSV público
y documentado que se pueda depender de él sin riesgo de que cambie sin aviso.
Además da sobre todo **observación** (lo que ha pasado), y aquí hace falta
**predicción** (lo que va a pasar).

### Opción C — Instituto Hidrográfico de la Marina · **ELEGIDA**

**Endpoint:** `https://ideihm.covam.es/api-ihm/getmarea`

Parámetros verificados:

| Parámetro | Valores | Notas |
|---|---|---|
| `request` | `getlist` | `gettide` | listado de estaciones / predicción |
| `id` o `port` | numérico / nombre corto | identificador de estación |
| `format` | `json`, `xml`, `txt`, `gra` | usamos json |
| `date` | `YYYYMMDD` | un día |
| `month` | `YYYYMM` | mes completo — es lo que usamos |

Sin clave de API. Sin registro.

**Respuesta real** para Chipiona el 14/08/2026 (`id=39`), copiada literalmente:

```json
{"mareas": {"copyright":"© Instituto Hidrográfico de la Marina (2026)",
 "id":"39", "puerto": "Chipiona", "fecha": "2026-08-14", "ndatos": "4",
 "lat": "36.746667", "lon": "-6.428333",
 "datos": { "marea": [
   {"hora": "03:03", "altura": "3.441", "tipo": "pleamar"},
   {"hora": "08:52", "altura": "0.451", "tipo": "bajamar"},
   {"hora": "15:19", "altura": "3.745", "tipo": "pleamar"},
   {"hora": "21:25", "altura": "0.379", "tipo": "bajamar"}]}}}
```

**Estaciones disponibles en la provincia** (todas verificadas contra
`request=getlist`):

| id | estación | usada por |
|---|---|---|
| 37 | Bonanza (Sanlúcar de Barrameda) | Sanlúcar |
| 39 | **Chipiona** | Chipiona |
| 40 | Rota | Rota |
| 41 | El Puerto de Santa María | Valdelagrana |
| 42 | Cádiz | Cádiz |
| 43 | La Carraca | Puerto Real |
| 44 | Gallineras | San Fernando (Camposoto) |
| 45 | Sancti Petri | Sancti Petri |
| 46 | Conil | — (disponible) |
| 47 | Barbate | — (disponible) |
| 48 | Tarifa | — (disponible) |
| 49 | Algeciras | — (disponible) |

Es decir: **la costa hasta Tarifa ya está cubierta por la fuente**. Añadir esos
spots es rellenar un bloque en `config/spots.yaml`, sin tocar código.

#### Lo que el IHM **no** da, y cómo se resuelve

**Sólo devuelve extremos** (pleamares y bajamares), no una serie horaria. Para
saber la altura a las 14:00 hay que interpolar. Se usa interpolación
semi-cosenoidal entre extremos consecutivos:

```
h(t) = (H1+H2)/2 + (H1-H2)/2 · cos( π · (t-t1)/(t2-t1) )
```

Es el equivalente continuo de la regla de los doceavos náutica. Exacta en los
extremos, con error de pocos centímetros en el tramo central para una marea
semidiurna como la gaditana. **Suficiente para decidir si se navega,
insuficiente para navegación náutica** — y así está documentado en el código.

#### Suposiciones pendientes de confirmar

1. **Zona horaria.** Se asume que el IHM publica en hora local peninsular
   (`Europe/Madrid`). Es lo coherente con sus tablas publicadas, pero no
   aparece declarado en la respuesta. `lib/tides.py` acepta un
   `offset_minutes` configurable por si hubiera que corregirlo, y
   `verify_apis.py` contrasta la fase contra Open-Meteo y falla si la
   diferencia supera 2 h.
2. **Datum.** Se asume el cero del puerto (aprox. bajamar máxima viva
   equinoccial), que es el de las tablas de marea al uso. La respuesta no
   declara ni unidades ni datum. Los valores observados (0,35–3,81 m en
   Chipiona) son coherentes con un rango mareal gaditano medido desde el cero
   del puerto.

**Licencia:** reutilización bajo Ley 37/2007 y RD 1495/2011, modalidad
**"reutilización con licencia para uso no comercial"**. La página de licencias
del IdeIHM dice literalmente: *"No se autoriza el uso comercial de ninguna
información contenida en este geoportal ni en ninguno de sus servicios."*
Obliga a citar la fuente (está en el pie del sitio).

---

## 4. Lo que NO se pudo verificar en esta sesión

Las peticiones en vivo a Open-Meteo no se pudieron ejecutar desde el entorno de
desarrollo de esta sesión: el proxy de salida no tenía sus dominios en la lista
permitida y `api.open-meteo.com/robots.txt` bloquea a los agentes de fetch.
Los endpoints, nombres de variables, unidades y límites de arriba salen de la
**documentación oficial**, no de una respuesta real.

Las respuestas del IHM **sí** se obtuvieron y verificaron en vivo, y están
copiadas literalmente en este documento y en los tests.

Por eso `scripts/verify_apis.py` se ejecuta como paso obligatorio del workflow,
**antes** de construir nada: la primera ejecución en GitHub Actions es la que
cierra la verificación de Open-Meteo contra la API real. Si algo no cuadra, el
despliegue se detiene y no se publica.
