# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


QML_IMPORTS = "import QtQuick 2.15\nimport QtQuick.Controls 2.15\nimport QtQuick.Layouts 1.15\n"


def qml_button() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\n"
        + "width: 512\nheight: 160\n"
        + "color: Qt.rgba(0, 0, 0, 0)\n"
        + "property string buttonText: \"Button\"\n"
        + "property int clickCount: 0\n"
        + "property bool checked: false\n"
        + "property bool checkable: false\n"
        + "property int fontSize: 28\n"
        + "Button {\nanchors.fill: parent\ntext: root.buttonText\n"
        + "checkable: root.checkable\nchecked: root.checked\n"
        + "font.pixelSize: root.fontSize\n"
        + "onClicked: { root.clickCount += 1\nroot.checked = checked }\n}\n}\n"
    )


def qml_label() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\nwidth: 512\nheight: 128\n"
        + "color: Qt.rgba(0, 0, 0, 0)\n"
        + "property string labelText: \"Label\"\n"
        + "property int fontSize: 32\n"
        + "property string textColor: \"white\"\n"
        + "property int hAlign: 1\n"
        + "Text {\nanchors.fill: parent\ntext: root.labelText\n"
        + "font.pixelSize: root.fontSize\ncolor: root.textColor\n"
        + "horizontalAlignment: root.hAlign\nverticalAlignment: Text.AlignVCenter\n"
        + "wrapMode: Text.WordWrap\n}\n}\n"
    )


def qml_slider() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\nwidth: 512\nheight: 128\n"
        + "color: Qt.rgba(0, 0, 0, 0)\n"
        + "property real sliderValue: 0.5\n"
        + "property real sliderMin: 0.0\n"
        + "property real sliderMax: 1.0\n"
        + "property real sliderStep: 0.01\n"
        + "Slider {\nanchors.fill: parent\n"
        + "from: root.sliderMin\nto: root.sliderMax\nstepSize: root.sliderStep\n"
        + "value: root.sliderValue\n"
        + "onMoved: { root.sliderValue = value }\n}\n}\n"
    )


def qml_textfield() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\nwidth: 512\nheight: 128\n"
        + "color: Qt.rgba(0, 0, 0, 0)\n"
        + "property string fieldText: \"\"\n"
        + "property string fieldPlaceholder: \"Type here\"\n"
        + "property int fieldMaxLen: 256\n"
        + "TextField {\nanchors.fill: parent\ntext: root.fieldText\n"
        + "placeholderText: root.fieldPlaceholder\n"
        + "maximumLength: root.fieldMaxLen\nfont.pixelSize: 28\n"
        + "onTextChanged: { root.fieldText = text }\n}\n}\n"
    )


def qml_checkbox() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\nwidth: 512\nheight: 128\n"
        + "color: Qt.rgba(0, 0, 0, 0)\n"
        + "property string boxText: \"Check\"\n"
        + "property bool boxChecked: false\n"
        + "CheckBox {\nanchors.fill: parent\ntext: root.boxText\n"
        + "checked: root.boxChecked\nfont.pixelSize: 28\n"
        + "onToggled: { root.boxChecked = checked }\n}\n}\n"
    )


def qml_progressbar() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\nwidth: 512\nheight: 96\n"
        + "color: Qt.rgba(0, 0, 0, 0)\n"
        + "property real barValue: 0.5\n"
        + "property real barMin: 0.0\n"
        + "property real barMax: 1.0\n"
        + "property bool barBusy: false\n"
        + "ProgressBar {\nanchors.fill: parent\n"
        + "from: root.barMin\nto: root.barMax\nvalue: root.barValue\n"
        + "indeterminate: root.barBusy\n}\n}\n"
    )


def qml_switch() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\nwidth: 384\nheight: 128\n"
        + "color: Qt.rgba(0, 0, 0, 0)\n"
        + "property string switchText: \"Switch\"\n"
        + "property bool switchChecked: false\n"
        + "Switch {\nanchors.fill: parent\ntext: root.switchText\n"
        + "checked: root.switchChecked\nfont.pixelSize: 28\n"
        + "onToggled: { root.switchChecked = checked }\n}\n}\n"
    )


def qml_dial() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\nwidth: 256\nheight: 256\n"
        + "color: Qt.rgba(0, 0, 0, 0)\n"
        + "property real dialValue: 0.5\n"
        + "property real dialMin: 0.0\n"
        + "property real dialMax: 1.0\n"
        + "property real dialStep: 0.01\n"
        + "Dial {\nanchors.centerIn: parent\nwidth: 220\nheight: 220\n"
        + "from: root.dialMin\nto: root.dialMax\nstepSize: root.dialStep\n"
        + "value: root.dialValue\n"
        + "onMoved: { root.dialValue = value }\n}\n}\n"
    )


def qml_combobox() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\nwidth: 512\nheight: 128\n"
        + "color: Qt.rgba(0, 0, 0, 0)\n"
        + "property int comboIndex: 0\n"
        + "property string comboItems: \"One|Two|Three\"\n"
        + "ComboBox {\nanchors.fill: parent\n"
        + "model: root.comboItems.split(\"|\")\n"
        + "currentIndex: root.comboIndex\nfont.pixelSize: 26\n"
        + "onActivated: { root.comboIndex = index }\n}\n}\n"
    )


def qml_spinbox() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\nwidth: 384\nheight: 128\n"
        + "color: Qt.rgba(0, 0, 0, 0)\n"
        + "property int spinValue: 0\n"
        + "property int spinMin: -100\n"
        + "property int spinMax: 100\n"
        + "SpinBox {\nanchors.fill: parent\n"
        + "from: root.spinMin\nto: root.spinMax\nvalue: root.spinValue\n"
        + "onValueChanged: { root.spinValue = value }\n}\n}\n"
    )


def qml_panel() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\nwidth: 512\nheight: 384\n"
        + "color: Qt.rgba(0.16, 0.18, 0.22, 0.92)\n"
        + "radius: 18\nborder.width: 2\nborder.color: \"lightsteelblue\"\n"
        + "property string panelTitle: \"Panel\"\n"
        + "property string panelColor: \"slategray\"\n"
        + "property int panelRadius: 18\n"
        + "Text {\nanchors.centerIn: parent\ntext: root.panelTitle\n"
        + "font.pixelSize: 34\ncolor: \"white\"\n}\n}\n"
    )


def qml_imageview() -> str:
    return (
        QML_IMPORTS
        + "Rectangle {\n"
        + "id: root\nwidth: 512\nheight: 512\n"
        + "color: Qt.rgba(0, 0, 0, 0)\n"
        + "property string imageSource: \"\"\n"
        + "property int imageFill: 1\n"
        + "Image {\nanchors.fill: parent\nsource: root.imageSource\n"
        + "fillMode: root.imageFill\ncache: true\nasynchronous: true\n}\n}\n"
    )


QML_DEFAULTS: dict = {
    "QuickButton": qml_button,
    "QuickLabel": qml_label,
    "QuickSlider": qml_slider,
    "QuickTextField": qml_textfield,
    "QuickCheckBox": qml_checkbox,
    "QuickProgressBar": qml_progressbar,
    "QuickSwitch": qml_switch,
    "QuickDial": qml_dial,
    "QuickComboBox": qml_combobox,
    "QuickSpinBox": qml_spinbox,
    "QuickPanel": qml_panel,
    "QuickImageView": qml_imageview,
}


def default_qml_for(class_name: str) -> str:
    maker = QML_DEFAULTS.get(class_name)
    if maker is None:
        return qml_panel()
    return maker()
