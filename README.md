# ARINC-429-completo

Aplicacion de escritorio para administrar instrumentos aeronáuticos, generar
palabras ARINC 429 configuradas por instrumento y registrar las salidas seriales
y de audio. Los datos se guardan en SQLite.

## Arquitectura

El proyecto usa arquitectura por capas:

- `domain/`: instrumentos, envíos, validación de rango y codificación de
  palabras ARINC 429.
- `application/`: servicios de casos de uso para instrumentos y envíos.
- `infrastructure/`: repositorios SQLite, salida serial PySerial y señal de
  audio generada con NumPy y reproducida con SoundDevice.
- `presentation/`: interfaz PySide6 con gestión de instrumentos, generación,
  salidas e historial.
- `tests/`: pruebas automatizadas sin requerir puertos seriales ni equipos
  físicos.

La base de datos se crea en
`~/.local/share/arinc429-completo/arinc429.sqlite3` en Linux,
`~/Library/Application Support/arinc429-completo/arinc429.sqlite3` en macOS y
`%APPDATA%/arinc429-completo/arinc429.sqlite3` en Windows.

## Requisitos

- Python 3.11 o posterior.
- Salida de audio disponible para reproducir señales.
- Un puerto serial disponible para probar esa salida.

## Instalación

Desde la raíz del repositorio, crea y activa un entorno virtual:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

En Windows, activa el entorno con:

```powershell
.venv\Scripts\Activate.ps1
```

Instala el proyecto y sus dependencias:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

Las dependencias principales son PySide6, PySerial, NumPy, SoundDevice y Pytest.
SoundDevice puede requerir PortAudio y un dispositivo de audio habilitado por
el sistema operativo.

## Ejecución y pruebas

```bash
python -m arinc429
python -m pytest
```

También se instala el comando `arinc429`.

## Configuración de codificación por instrumento

El sistema no asigna escalas, orden de bits, signo, etiquetas ni mapas de
discretas por suposición. Al generar una palabra, solicita una configuración
JSON según la documentación del instrumento; la generación se rechaza mientras
falte un campo o el dato no sea representable.

Todos los formatos requieren:

- `label_base`: `octal`, `decimal`, `hexadecimal` o `binary`; determina cómo se
  interpreta el campo Label almacenado en el instrumento.
- `label_bit_order`: `normal` o `reversed`.
- `parity`: `odd` o `even`.

Dentro de `data`, la codificación BNR utiliza `resolution` del instrumento como
su LSB y requiere `zero_value`, `representation` (`unsigned`,
`twos_complement` o `sign_magnitude`) y `data_bit_positions`, una lista
explícita de 19 destinos de bit, del bit
numérico menos significativo al más significativo. Para `sign_magnitude`
también se requiere `sign_bit_position`.

BCD requiere `decimal_places` y `digit_bit_positions`: una lista de grupos de
cuatro posiciones de bit por dígito, empezando por el dígito menos
significativo. Cada posición es un índice de 0 a 18 (0 corresponde al bit 11 de
la palabra) y los grupos no pueden superponerse. Si el instrumento admite
valores negativos, se debe proporcionar además el mapa explícito `sign` con
`position`, `negative_value` y `positive_value`.

La codificación discreta requiere un `value_map` explícito que asocie cada
valor permitido (como texto numérico) con su patrón de datos entero de 19 bits.
No se genera un patrón para estados no definidos.

SDI y SSM se configuran como valores de 0 a 3 en el instrumento. La interfaz
muestra la palabra de 32 bits en binario y hexadecimal cuando todos los datos
son válidos.

## Salidas y límites físicos

La salida serial usa PySerial. Los valores iniciales son 115200 baudios, 8N1;
el puerto, baudios, bits de datos, paridad y bits de parada se pueden configurar
en la interfaz. Cada palabra se envía en cuatro bytes consecutivos en orden Big
Endian. El historial conserva la configuración, los bytes y el resultado
informado por la escritura serial. Una UART serial **no es** un transmisor de
línea ARINC 429 y no debe conectarse directamente al bus sin una interfaz
eléctrica compatible.

La salida de audio es un tono senoidal mono de 44100 muestras/s, 16 bits,
inicialmente 1000 Hz, amplitud digital al 50 % y duración de un segundo. Se
pueden ajustar frecuencia, amplitud y duración. El nivel digital no garantiza
una tensión física: depende de la tarjeta de sonido, el control de volumen y la
carga. La salida de auriculares es analógica y **no es compatible directamente
con el bus ARINC 429**.
