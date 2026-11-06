import json
import sqlite3
from dataclasses import replace

import serial
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from arinc429.application.services import InstrumentService, TransmissionService
from arinc429.domain.models import EncodingType, Instrument, Transmission
from arinc429.domain.word import ArincWord
from arinc429.infrastructure.audio_output import AudioOutput, AudioOutputError
from arinc429.infrastructure.database import (
    Database,
    InstrumentRepository,
    TransmissionRepository,
)
from arinc429.infrastructure.serial_output import SerialOutput, SerialSettings

CONFIG_HINTS = {
    EncodingType.BNR: {
        "label_base": None,
        "label_bit_order": None,
        "parity": None,
        "data": {
            "zero_value": None,
            "representation": None,
            "data_bit_positions": [],
            "sign_bit_position": None,
        },
    },
    EncodingType.BCD: {
        "label_base": None,
        "label_bit_order": None,
        "parity": None,
        "data": {
            "decimal_places": None,
            "digit_bit_positions": [],
            "sign": {
                "position": None,
                "negative_value": None,
                "positive_value": None,
            },
        },
    },
    EncodingType.DISCRETE: {
        "label_base": None,
        "label_bit_order": None,
        "parity": None,
        "data": {"value_map": {}},
    },
}


class InstrumentDialog(QDialog):
    def __init__(
        self, parent: QWidget, instrument: Instrument | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Instrumento")
        self._instrument = instrument
        layout = QFormLayout(self)
        self.name = QLineEdit()
        self.minimum = self._number_input()
        self.maximum = self._number_input()
        self.label = QLineEdit()
        self.encoding = QComboBox()
        for encoding in EncodingType:
            self.encoding.addItem(encoding.value, encoding)
        self.resolution = self._number_input(0.000001)
        self.unit = QLineEdit()
        self.sdi = QSpinBox()
        self.sdi.setRange(0, 3)
        self.ssm = QSpinBox()
        self.ssm.setRange(0, 3)
        self.config = QPlainTextEdit()
        self.config.setPlaceholderText(
            "Opcional al registrar. Se solicitará antes de generar una palabra."
        )
        self.config.setMinimumHeight(130)

        for label, field in (
            ("Nombre", self.name),
            ("Valor mínimo", self.minimum),
            ("Valor máximo", self.maximum),
            ("Label (texto)", self.label),
            ("Codificación", self.encoding),
            ("Resolución / factor", self.resolution),
            ("Unidad", self.unit),
            ("SDI (0–3)", self.sdi),
            ("SSM (0–3)", self.ssm),
            ("Configuración explícita (JSON)", self.config),
        ):
            layout.addRow(label, field)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        if instrument:
            self._load(instrument)

    @staticmethod
    def _number_input(minimum: float = -1_000_000_000) -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(minimum, 1_000_000_000)
        field.setDecimals(6)
        field.setKeyboardTracking(False)
        return field

    def _load(self, instrument: Instrument) -> None:
        self.name.setText(instrument.name)
        self.minimum.setValue(instrument.minimum)
        self.maximum.setValue(instrument.maximum)
        self.label.setText(instrument.label)
        self.encoding.setCurrentIndex(
            self.encoding.findData(instrument.encoding)
        )
        self.resolution.setValue(instrument.resolution)
        self.unit.setText(instrument.unit)
        self.sdi.setValue(instrument.sdi)
        self.ssm.setValue(instrument.ssm)
        self.config.setPlainText(instrument.encoding_config or "")

    def instrument(self) -> Instrument:
        config = self.config.toPlainText().strip() or None
        if config is not None:
            try:
                json.loads(config)
            except json.JSONDecodeError as error:
                raise ValueError(f"JSON inválido: {error.msg}.") from error
        return Instrument(
            id=self._instrument.id if self._instrument else None,
            name=self.name.text(),
            minimum=self.minimum.value(),
            maximum=self.maximum.value(),
            label=self.label.text(),
            encoding=self.encoding.currentData(),
            resolution=self.resolution.value(),
            unit=self.unit.text(),
            sdi=self.sdi.value(),
            ssm=self.ssm.value(),
            encoding_config=config,
        )


class TransmissionDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        instruments: list[Instrument],
        transmission: Transmission,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modificar envío")
        layout = QFormLayout(self)
        self.instrument = QComboBox()
        for instrument in instruments:
            self.instrument.addItem(
                f"{instrument.name} (#{instrument.id})",
                instrument.id,
            )
        self.instrument.setCurrentIndex(
            self.instrument.findData(transmission.instrument_id)
        )
        self.value = QDoubleSpinBox()
        self.value.setRange(-1_000_000_000, 1_000_000_000)
        self.value.setDecimals(6)
        self.value.setValue(transmission.value)
        layout.addRow("Instrumento", self.instrument)
        layout.addRow("Valor", self.value)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class EncodingConfigDialog(QDialog):
    def __init__(
        self, parent: QWidget, title: str, instruction: str, config: str
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        label = QLabel(instruction)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(config)
        self.editor.setMinimumSize(720, 430)
        layout.addWidget(self.editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self, database: Database | None = None) -> None:
        super().__init__()
        self.setWindowTitle("ARINC-429-completo")
        self.resize(1100, 760)
        self.database = database or Database()
        self.instrument_repository = InstrumentRepository(self.database)
        self.transmission_repository = TransmissionRepository(self.database)
        self.instruments = InstrumentService(self.instrument_repository)
        self.transmissions = TransmissionService(
            self.instrument_repository, self.transmission_repository
        )
        self.serial_output = SerialOutput()
        self.audio_output = AudioOutput()
        self.current_word: ArincWord | None = None
        self.current_transmission: Transmission | None = None
        self.current_instrument: Instrument | None = None
        self.current_value = 0.0
        self._build_ui()
        self.refresh_instruments()
        self.refresh_history()

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._instrument_tab(), "Instrumentos")
        tabs.addTab(self._transmission_tab(), "Envíos")
        tabs.addTab(self._audio_tab(), "Salida de audio")
        self.setCentralWidget(tabs)

    def _instrument_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.instrument_table = QTableWidget(0, 9)
        self.instrument_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Nombre",
                "Mínimo",
                "Máximo",
                "Label",
                "Codificación",
                "Resolución",
                "Unidad",
                "Config.",
            ]
        )
        self.instrument_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.instrument_table)
        buttons = QHBoxLayout()
        add_button = QPushButton("Agregar")
        edit_button = QPushButton("Modificar")
        delete_button = QPushButton("Eliminar")
        add_button.clicked.connect(self.add_instrument)
        edit_button.clicked.connect(self.edit_instrument)
        delete_button.clicked.connect(self.delete_instrument)
        buttons.addWidget(add_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(delete_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        return widget

    def _transmission_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        form = QFormLayout()
        self.instrument_combo = QComboBox()
        self.instrument_combo.currentIndexChanged.connect(
            self._invalidate_current_word
        )
        self.transmission_value = QDoubleSpinBox()
        self.transmission_value.setRange(-1_000_000_000, 1_000_000_000)
        self.transmission_value.setDecimals(6)
        self.transmission_value.valueChanged.connect(
            self._invalidate_current_word
        )
        form.addRow("Instrumento", self.instrument_combo)
        form.addRow("Valor", self.transmission_value)
        layout.addLayout(form)
        action_row = QHBoxLayout()
        generate_button = QPushButton("Generar palabra")
        self.serial_port = QComboBox()
        self.serial_port.setEditable(True)
        self.serial_port.setPlaceholderText("Seleccione o escriba el puerto")
        refresh_ports = QPushButton("Actualizar puertos")
        serial_button = QPushButton("Transmitir por serial")
        self.serial_baudrate = QSpinBox()
        self.serial_baudrate.setRange(50, 4_000_000)
        self.serial_baudrate.setValue(115200)
        self.serial_bytesize = QComboBox()
        for size in (5, 6, 7, 8):
            self.serial_bytesize.addItem(str(size), size)
        self.serial_bytesize.setCurrentIndex(
            self.serial_bytesize.findData(8)
        )
        self.serial_parity = QComboBox()
        for label, parity in (
            ("Ninguna", serial.PARITY_NONE),
            ("Par", serial.PARITY_EVEN),
            ("Impar", serial.PARITY_ODD),
        ):
            self.serial_parity.addItem(label, parity)
        self.serial_stopbits = QComboBox()
        for stopbits in (
            serial.STOPBITS_ONE,
            serial.STOPBITS_ONE_POINT_FIVE,
            serial.STOPBITS_TWO,
        ):
            self.serial_stopbits.addItem(str(stopbits), stopbits)
        self.serial_stopbits.setCurrentIndex(
            self.serial_stopbits.findData(serial.STOPBITS_ONE)
        )
        generate_button.clicked.connect(self.generate_current_word)
        refresh_ports.clicked.connect(self.refresh_serial_ports)
        serial_button.clicked.connect(self.transmit_serial)
        action_row.addWidget(generate_button)
        action_row.addWidget(QLabel("Puerto:"))
        action_row.addWidget(self.serial_port, 1)
        action_row.addWidget(refresh_ports)
        action_row.addWidget(serial_button)
        layout.addLayout(action_row)
        serial_config = QHBoxLayout()
        serial_config.addWidget(QLabel("Baudios:"))
        serial_config.addWidget(self.serial_baudrate)
        serial_config.addWidget(QLabel("Bits:"))
        serial_config.addWidget(self.serial_bytesize)
        serial_config.addWidget(QLabel("Paridad:"))
        serial_config.addWidget(self.serial_parity)
        serial_config.addWidget(QLabel("Parada:"))
        serial_config.addWidget(self.serial_stopbits)
        serial_config.addStretch()
        layout.addLayout(serial_config)
        self.serial_settings_label = QLabel(
            "Valores iniciales: 115200 baudios, 8N1. Palabra de 32 bits en 4 bytes "
            "Big Endian. Una UART no es una interfaz eléctrica ARINC 429."
        )
        self.serial_settings_label.setWordWrap(True)
        layout.addWidget(self.serial_settings_label)
        self.word_view = QLabel("Genere una palabra con la configuración del instrumento.")
        self.word_view.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.word_view.setWordWrap(True)
        layout.addWidget(self.word_view)
        layout.addWidget(QLabel("Historial de envíos y resultados:"))
        self.history_table = QTableWidget(0, 8)
        self.history_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Fecha UTC",
                "Instrumento",
                "Valor",
                "Salida",
                "Resultado",
                "Palabra",
                "Detalle",
            ]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.history_table, 1)
        history_buttons = QHBoxLayout()
        edit_button = QPushButton("Modificar envío")
        delete_button = QPushButton("Eliminar envío")
        edit_button.clicked.connect(self.edit_transmission)
        delete_button.clicked.connect(self.delete_transmission)
        history_buttons.addWidget(edit_button)
        history_buttons.addWidget(delete_button)
        history_buttons.addStretch()
        layout.addLayout(history_buttons)
        return widget

    def _invalidate_current_word(self, *_args: object) -> None:
        self.current_word = None
        self.current_transmission = None
        self.current_instrument = None
        self.word_view.setText(
            "Genere una palabra con la configuración del instrumento."
        )

    def _audio_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        form = QFormLayout()
        self.audio_frequency = QDoubleSpinBox()
        self.audio_frequency.setRange(1, 22049)
        self.audio_frequency.setValue(1000)
        self.audio_frequency.setSuffix(" Hz")
        self.audio_amplitude = QSpinBox()
        self.audio_amplitude.setRange(0, 100)
        self.audio_amplitude.setValue(50)
        self.audio_amplitude.setSuffix(" %")
        self.audio_duration = QDoubleSpinBox()
        self.audio_duration.setRange(0.05, 60)
        self.audio_duration.setDecimals(2)
        self.audio_duration.setValue(1.0)
        self.audio_duration.setSuffix(" s")
        form.addRow("Frecuencia", self.audio_frequency)
        form.addRow("Amplitud", self.audio_amplitude)
        form.addRow("Duración", self.audio_duration)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        play_button = QPushButton("Reproducir")
        stop_button = QPushButton("Detener")
        play_button.clicked.connect(self.play_audio)
        stop_button.clicked.connect(self.stop_audio)
        buttons.addWidget(play_button)
        buttons.addWidget(stop_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        note = QLabel(
            "Esta función genera un tono senoidal mono de audio (44100 Hz de "
            "muestreo, 16 bits, inicialmente 1 kHz, 50 % y 1 segundo). El control "
            "de amplitud es digital; la tensión real depende de la tarjeta de "
            "sonido, el volumen del sistema y la carga conectada. Esta salida "
            "analógica de auriculares NO es una salida eléctrica ARINC 429 y no "
            "debe conectarse directamente a un bus ARINC 429."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return widget

    def refresh_instruments(self) -> None:
        instruments = self.instruments.list_instruments()
        self.instrument_table.setRowCount(len(instruments))
        for row, instrument in enumerate(instruments):
            values = (
                str(instrument.id),
                instrument.name,
                f"{instrument.minimum:g}",
                f"{instrument.maximum:g}",
                instrument.label,
                instrument.encoding.value,
                f"{instrument.resolution:g}",
                instrument.unit,
                "Completa" if instrument.encoding_config else "Pendiente",
            )
            for column, value in enumerate(values):
                self.instrument_table.setItem(
                    row, column, QTableWidgetItem(value)
                )
        self.instrument_combo.clear()
        for instrument in instruments:
            self.instrument_combo.addItem(
                f"{instrument.name} (#{instrument.id})",
                instrument.id,
            )

    def refresh_history(self) -> None:
        transmissions = self.transmissions.list_transmissions()
        self.history_table.setRowCount(len(transmissions))
        for row, transmission in enumerate(transmissions):
            values = (
                str(transmission.id),
                transmission.created_at,
                transmission.instrument_name,
                f"{transmission.value:g}",
                transmission.output,
                transmission.status,
                transmission.word_hex,
                transmission.details,
            )
            for column, value in enumerate(values):
                self.history_table.setItem(
                    row, column, QTableWidgetItem(value)
                )

    def _selected_instrument(self) -> Instrument | None:
        row = self.instrument_table.currentRow()
        if row < 0:
            return None
        item = self.instrument_table.item(row, 0)
        return self.instruments.get(int(item.text())) if item else None

    def add_instrument(self) -> None:
        dialog = InstrumentDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.instruments.save_instrument(dialog.instrument())
            self.refresh_instruments()
        except (ValueError, sqlite3.Error) as error:
            self._show_error(str(error))

    def edit_instrument(self) -> None:
        instrument = self._selected_instrument()
        if instrument is None:
            self._show_error("Seleccione un instrumento.")
            return
        dialog = InstrumentDialog(self, instrument)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.instruments.save_instrument(dialog.instrument())
            self.refresh_instruments()
            self.refresh_history()
        except (ValueError, sqlite3.Error) as error:
            self._show_error(str(error))

    def delete_instrument(self) -> None:
        instrument = self._selected_instrument()
        if instrument is None or instrument.id is None:
            self._show_error("Seleccione un instrumento.")
            return
        answer = QMessageBox.question(
            self,
            "Eliminar instrumento",
            f"¿Eliminar '{instrument.name}'? El historial asociado se conservará.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.instruments.delete_instrument(instrument.id)
            self.refresh_instruments()
            self.refresh_history()
        except sqlite3.Error as error:
            self._show_error(str(error))

    def _request_encoding_config(self, instrument: Instrument) -> Instrument | None:
        existing = instrument.encoding_config
        if existing:
            initial_text = existing
        else:
            initial_text = json.dumps(
                CONFIG_HINTS[instrument.encoding], indent=2, ensure_ascii=False
            )
        dialog = EncodingConfigDialog(
            self,
            f"Configurar {instrument.name}",
            "Complete todos los parámetros según la especificación del instrumento. "
            "Los valores null/listas vacías no definen una codificación. "
            "No se genera la palabra hasta que la configuración sea válida.",
            initial_text,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        config = dialog.editor.toPlainText().strip()
        try:
            parsed_config = json.loads(config)
            if not isinstance(parsed_config, dict):
                raise ValueError("La configuración debe ser un objeto JSON.")
            updated = self.instruments.save_instrument(
                replace(instrument, encoding_config=config)
            )
            self.refresh_instruments()
            return updated
        except (ValueError, sqlite3.Error) as error:
            self._show_error(str(error))
            return None

    def generate_current_word(self) -> None:
        self._invalidate_current_word()
        instrument_id = self.instrument_combo.currentData()
        if instrument_id is None:
            self._show_error("Registre o seleccione un instrumento.")
            return
        instrument = self.instruments.get_instrument(instrument_id)
        if instrument is None:
            self._show_error("El instrumento seleccionado ya no existe.")
            return
        value = self.transmission_value.value()
        try:
            instrument.validate_value(value)
        except ValueError as error:
            self._show_error(str(error))
            return
        try:
            word = self.instruments.generate_word(instrument_id, value)
        except ValueError:
            instrument = self._request_encoding_config(instrument)
            if instrument is None:
                return
            try:
                word = self.instruments.generate_word(instrument_id, value)
            except ValueError as config_error:
                self._show_error(str(config_error))
                return
        try:
            record = self.transmissions.create_transmission(
                instrument_id,
                value,
                output="Sin transmitir",
                status="Palabra generada",
                details="",
                word_hex=word.hexadecimal,
                word_binary=word.binary,
            )
        except (ValueError, sqlite3.Error) as error:
            self._show_error(str(error))
            return
        self.current_word = word
        self.current_transmission = record
        self.current_instrument = instrument
        self.current_value = value
        self.word_view.setText(
            f"Instrumento: {instrument.name} | Valor: {value:g} {instrument.unit}\n"
            f"Binario: {word.binary}\nHexadecimal: {word.hexadecimal}\n"
            "Serial: cuatro bytes en Big Endian."
        )
        self.refresh_history()

    def refresh_serial_ports(self) -> None:
        selected = self.serial_port.currentText()
        self.serial_port.clear()
        self.serial_port.addItems(self.serial_output.available_ports())
        if selected:
            self.serial_port.setCurrentText(selected)

    def transmit_serial(self) -> None:
        if self.current_word is None or self.current_transmission is None:
            self._show_error("Genere una palabra válida antes de transmitir.")
            return
        port = self.serial_port.currentText().strip()
        if not port:
            self._show_error("Seleccione o escriba un puerto serial.")
            return
        settings = SerialSettings(
            port=port,
            baudrate=self.serial_baudrate.value(),
            bytesize=self.serial_bytesize.currentData(),
            parity=self.serial_parity.currentData(),
            stopbits=self.serial_stopbits.currentData(),
        )
        framing = (
            f"{settings.baudrate} baudios, {settings.bytesize}"
            f"{settings.parity}{settings.stopbits:g}"
        )
        try:
            bytes_hex = self.serial_output.transmit(self.current_word, settings)
            self.current_transmission = self.transmissions.record_output_event(
                output="Serial",
                value=self.current_value,
                status="Escritura serial completada",
                details=(
                    f"Puerto {port}; {framing}; bytes Big Endian: {bytes_hex}. "
                    "La escritura local no confirma recepción en un bus ARINC 429."
                ),
                instrument_id=self.current_instrument.id
                if self.current_instrument
                else None,
                instrument_name=self.current_instrument.name
                if self.current_instrument
                else "Instrumento no disponible",
                word_hex=self.current_word.hexadecimal,
                word_binary=self.current_word.binary,
            )
            QMessageBox.information(
                self,
                "Transmisión serial",
                f"Escritura serial completada.\nBytes: {bytes_hex}\n"
                "La escritura local no confirma recepción en un bus ARINC 429.",
            )
        except (serial.SerialException, OSError, ValueError) as error:
            try:
                self.current_transmission = self.transmissions.record_output_event(
                    output="Serial",
                    value=self.current_value,
                    status="Error",
                    details=f"Puerto {port}; {framing}; {error}",
                    instrument_id=self.current_instrument.id
                    if self.current_instrument
                    else None,
                    instrument_name=self.current_instrument.name
                    if self.current_instrument
                    else "Instrumento no disponible",
                    word_hex=self.current_word.hexadecimal,
                    word_binary=self.current_word.binary,
                )
            except (ValueError, sqlite3.Error) as save_error:
                self._show_error(
                    f"Falló la transmisión ({error}) y no se pudo registrar "
                    f"el resultado ({save_error})."
                )
            else:
                self._show_error(f"Falló la transmisión serial: {error}")
        except sqlite3.Error as error:
            self._show_error(f"Transmisión realizada, pero falló el registro: {error}")
        self.refresh_history()

    def edit_transmission(self) -> None:
        row = self.history_table.currentRow()
        if row < 0:
            self._show_error("Seleccione un envío del historial.")
            return
        transmission_id = int(self.history_table.item(row, 0).text())
        transmission = self.transmissions.get_transmission(transmission_id)
        if transmission is None:
            self._show_error("El envío seleccionado ya no existe.")
            return
        if transmission.instrument_id is None:
            self._show_error(
                "Este registro de salida no está asociado a un envío de instrumento."
            )
            return
        instruments = self.instruments.list_instruments()
        if not instruments:
            self._show_error("No hay instrumentos disponibles.")
            return
        dialog = TransmissionDialog(self, instruments, transmission)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            instrument_id = dialog.instrument.currentData()
            if instrument_id is None:
                raise ValueError("Seleccione un instrumento.")
            instrument = self.instruments.get_instrument(instrument_id)
            if instrument is None:
                raise ValueError("El instrumento seleccionado ya no existe.")
            instrument.validate_value(dialog.value.value())
            updated = replace(
                transmission,
                instrument_id=instrument_id,
                instrument_name=instrument.name,
                value=dialog.value.value(),
                output="Pendiente",
                status="Modificado; requiere regenerar palabra",
                details="",
                word_hex="",
                word_binary="",
            )
            self.transmissions.update_transmission(updated)
            self.refresh_history()
        except (ValueError, sqlite3.Error) as error:
            self._show_error(str(error))

    def delete_transmission(self) -> None:
        row = self.history_table.currentRow()
        if row < 0:
            self._show_error("Seleccione un envío del historial.")
            return
        transmission_id = int(self.history_table.item(row, 0).text())
        answer = QMessageBox.question(
            self, "Eliminar envío", "¿Eliminar el registro seleccionado?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.transmissions.delete_transmission(transmission_id)
            self.refresh_history()
        except sqlite3.Error as error:
            self._show_error(str(error))

    def play_audio(self) -> None:
        try:
            frequency = self.audio_frequency.value()
            amplitude = self.audio_amplitude.value() / 100
            duration = self.audio_duration.value()
            self.audio_output.play(
                frequency=frequency,
                amplitude=amplitude,
                duration=duration,
                sample_rate=44100,
            )
        except (ValueError, OSError, AudioOutputError) as error:
            self._show_error(f"No se pudo reproducir el audio: {error}")
            return
        try:
            self.transmissions.record_output_event(
                output="Audio",
                value=frequency,
                status="Reproducción iniciada",
                instrument_name="Tono de audio",
                details=(
                    f"Tono senoidal mono de {frequency:g} Hz; "
                    f"amplitud digital {amplitude:.0%}; "
                    f"duración {duration:g} s; 44100 Hz; PCM 16 bits."
                ),
            )
            self.refresh_history()
        except sqlite3.Error as error:
            self._show_error(
                f"El audio comenzó, pero no se pudo registrar en el historial: {error}"
            )

    def stop_audio(self) -> None:
        try:
            self.audio_output.stop()
        except (OSError, AudioOutputError) as error:
            self._show_error(f"No se pudo detener el audio: {error}")

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "ARINC-429-completo", message)
