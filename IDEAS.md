# Ideas aparcadas

Cosas que surgieron construyendo la Fase 1 y que se dejaron fuera a propósito.
No están descartadas: están anotadas para no perderlas.

Orden aproximado de "valor por esfuerzo", de más a menos.

---

## Casi gratis, mucho valor

**Extender la costa hasta Tarifa.**
El IHM ya tiene estaciones de marea para Conil (46), Barbate (47), Tarifa (48)
y Algeciras (49). Añadir El Palmar, Zahara, Los Caños, Valdevaqueros o Los
Lances es rellenar bloques en `spots.yaml`. Cero código.
Aviso: Tarifa es otro régimen de viento (Levante/Poniente, la marea pinta
mucho menos). Merece pensar sus direcciones y umbrales desde cero en vez de
copiar los de la bahía.

**Enlace directo a un spot.**
`?spot=chipiona` para poder mandarle a alguien el sitio ya abierto en su playa.
Diez líneas de JavaScript.

**"Mejor spot de hoy".**
Ya tenemos el veredicto de los 8 spots en el mismo JSON. Una línea arriba del
todo del tipo *"Hoy lo mejor está en Rota, 14:00–18:00"* sale casi gratis y
cambia el producto: pasa de "consulto mi playa" a "me dices dónde ir".

**Registro de calibración.**
Un campo `calibrado_el: 2026-08-20` por spot, y que la interfaz avise cuando
un spot lleva mucho sin revisarse. Barato y mantiene el activo vivo.

---

## Merece la pena, cuesta algo

**Aprender de la realidad.**
Un botón de "hoy salí / hoy no salí, y qué tal" que registre el veredicto que
dimos frente a lo que pasó de verdad. Con 30 o 40 registros se pueden ajustar
los umbrales con datos en vez de a ojo. Es el camino natural para calibrar sin
tener que adivinar.
Requiere guardar algo en alguna parte → rompe la restricción de "sin backend".
Alternativa sin servidor: guardarlo en `localStorage` y exportar un fichero
que se pegue en el repo. Feo pero funciona y sigue costando cero.

**Aviso cuando se den las condiciones.**
Lo que de verdad pide el problema: no consultar, que te avisen. Requiere push
o correo, y por tanto identidad y estado. Es el salto de Fase 1 a producto.
Camino más barato: un feed RSS por spot generado por el mismo cron. Cero coste,
cero cuentas, y quien quiera se suscribe.

**Diferencia entre modelos como medida de incertidumbre.**
Ahora la fiabilidad se deduce sólo del horizonte (día 1 vs día 5). Sería más
honesto comparar dos modelos (Open-Meteo sirve ICON, AROME y ECMWF por
separado) y usar su discrepancia: si coinciden, alta confianza; si no, dilo.
Coste: una llamada más por spot. Sigue muy por debajo del límite de uso.

**Marea por armónicos propios.**
Calcular la marea con constantes armónicas en local, sin depender de ninguna
API. Elimina la única dependencia con licencia restrictiva y funcionaría
offline y para siempre. Es la salida limpia al problema de licencias si algún
día hay patrocinio.

---

## Más adelante, o nunca

**Perfiles de material.**
Que el ala recomendada dependa también de la tabla y el foil, no sólo del
peso. Un rider con foil de 1600 cm² planea con dos nudos menos. Requiere un
modelo de material y probablemente cuentas de usuario.

**Vientos térmicos.**
En la bahía el térmico de la tarde es media temporada y los modelos globales
lo capturan regular. Una corrección local por spot y por mes, calibrada con
observación, sería un diferencial enorme. También es mucho trabajo manual.

**Estado del mar en tiempo real.**
Las boyas de Puertos del Estado dan observación real. Contrastar previsión con
observación de la última hora daría un "y ahora mismo, esto es lo que hay".
Bloqueado por la falta de una API con contrato estable.

**Mapa, comunidad, comentarios, partes de otros riders, app nativa.**
Fuera de alcance por decisión, no por dificultad. Cada uno de ellos convierte
un sitio estático en un servicio que hay que vigilar, y la restricción del
proyecto es mantenimiento cercano a cero.

---

## Lo que hay que resolver si alguna vez hay patrocinio

Las dos fuentes actuales son de uso no comercial y una web con publicidad las
incumple (ver README). Opciones, con su coste:

1. **Open-Meteo de pago** para meteo + **armónicos propios** para marea.
   Elimina el problema entero. La marea propia es trabajo de una tarde larga.
2. **AEMET OpenData** para meteo. Es gratuita y su licencia de reutilización es
   más permisiva que la del IHM, pero el formato es bastante más incómodo.
   Habría que verificarla en serio antes de prometer nada.
3. **Patrocinio como mecenazgo sin publicidad** (agradecimiento, no anuncio).
   Zona gris. No apoyarse en esto sin leerse las licencias con calma.

Nada de esto entra en Fase 1.
