import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

import "Model.js" as Model

Panel {
  id: root
  moduleName: "gotar.omarchy-themes"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null

  // shell-theme-aware palette
  readonly property color fg: barForeground
  readonly property color dim: Qt.darker(fg, 1.5)
  readonly property color faint: Qt.darker(fg, 2.2)
  readonly property color okC: "#8fd08a"
  readonly property color errC: "#e74c5b"
  readonly property string mono: Style.font.family

  // ---- data
  property var db: null                 // { base, fetchedAt, count, entries: [...] }
  property var filtered: []             // indexes into db.entries passing the filters
  property var facets: ({ tone: {}, color: {}, resMin: {}, resMax: {} })
  property string q: ""
  property string tone: ""
  property string color: ""
  property string resMin: ""
  property string resMax: ""
  property var crumbs: []

  property int phase: 0                 // 0 loading, 1 ready, 2 error
  property string phaseMsg: ""
  property string currentTheme: ""

  // ---- detail (variant picker)
  property int detailIdx: -1
  property string detailPath: ""
  property int detailVariant: 0
  property var detailVariants: []
  property int applyPhase: 0            // 0 none, 1 installing, 2 setting, 3 done, 4 error
  property string applySlug: ""
  property string applyMsg: ""
  property int cursorIdx: 0

  readonly property bool hasActiveFilters:
    q !== "" || tone !== "" || color !== "" || resMin !== "" || resMax !== ""
  readonly property string modeLabel:
    applyPhase > 0 ? "APPLY" :
    detailPath !== "" ? "VIEW" : "BROWSE"
  readonly property int gridCols: 4

  function scriptPath(name) {
    return Qt.resolvedUrl("bin/" + name).replace(/^file:\/\//, "")
  }
  function baseOf() { return db ? String(db.base || "") : "" }
  function url(rel) { return baseOf() + "/" + String(rel || "").replace(/^\/+/, "") }
  function entryAt(i) { return db && db.entries ? db.entries[i] : null }

  function setQuery(text) {
    root.q = String(text || "")
    qTimer.restart()
  }

  function buildCrumbs() {
    var c = []
    if (root.q) c.push({ key: "search", label: "q:\u0022" + root.q + "\u0022" })
    if (root.tone) c.push({ key: "tone", label: "tone:" + root.tone })
    if (root.color) c.push({ key: "color", label: "color:" + root.color })
    if (root.resMin || root.resMax) {
      var v
      if (root.resMin && root.resMax) v = "res:" + root.resMin + ".." + root.resMax
      else if (root.resMin) v = "res:\u2265" + root.resMin
      else v = "res:\u2264" + root.resMax
      c.push({ key: "res", label: v })
    }
    root.crumbs = c
  }

  function refreshFilters() {
    if (!root.db) return
    var res = Model.apply(root.db.entries, root.q, root.tone, root.color,
                          root.resMin, root.resMax)
    root.filtered = res.filtered
    root.facets = res.facets
    if (root.cursorIdx >= res.filtered.length)
      root.cursorIdx = Math.max(0, res.filtered.length - 1)
    root.buildCrumbs()
  }

  function toggleFacet(key, value) {
    if (key === "tone") root.tone = (root.tone === value) ? "" : value
    else if (key === "color") root.color = (root.color === value) ? "" : value
    else if (key === "res-min") root.resMin = (root.resMin === value) ? "" : value
    else if (key === "res-max") root.resMax = (root.resMax === value) ? "" : value
    root.refreshFilters()
  }

  function clearCrumb(key) {
    if (key === "search") { root.q = ""; searchField.text = "" }
    else if (key === "tone") root.tone = ""
    else if (key === "color") root.color = ""
    else if (key === "res") { root.resMin = ""; root.resMax = "" }
    root.refreshFilters()
  }

  function resetFilters() {
    root.tone = ""
    root.color = ""
    root.resMin = ""
    root.resMax = ""
    root.q = ""
    searchField.text = ""
    root.refreshFilters()
  }

  function startLoad(force) {
    if (fetchProc.running && !force) return
    root.phase = 0
    root.phaseMsg = force ? "re-fetching index (35 MB)\u2026" : "loading index\u2026"
    var sc="/home/gotar/.config/omarchy/plugins/gotar.omarchy-themes/bin/fetch-manifest.py"
    fetchProc.command = ["/usr/bin/python3", sc].concat(force ? ["--force"] : [])
    fetchWatchdog.start()
    fetchProc.running = true
  }

  function handleFetchOutput(text) {
    fetchWatchdog.stop()
    var j = null
    try { j = JSON.parse(text) } catch (e) { j = null }
    if (!j || j.error || !j.entries) {
      root.phase = 2
      root.phaseMsg = (j && j.error) ? String(j.error) : "bad manifest"
      return
    }
    root.db = j
    Model.prep(j.entries)
    root.phase = 1
    root.phaseMsg = ""
    root.cursorIdx = 0
    root.refreshFilters()
    root.loadCurrentTheme()
  }

  function loadCurrentTheme() {
    themeCurProc.command = ["omarchy", "theme", "current"]
    themeCurProc.running = true
  }

  function moveCursor(dx, dy) {
    var n = root.filtered.length
    if (!root.db || !n) return
    if (root.cursorIdx < 0) root.cursorIdx = 0
    if (root.cursorIdx >= n) root.cursorIdx = n - 1
    var cols = root.gridCols
    var row = Math.floor(root.cursorIdx / cols)
    var col = root.cursorIdx % cols
    var lastRow = Math.floor((n - 1) / cols)
    if (dy > 0) {
      row = Math.min(lastRow, row + 1)
      col = Math.min(col, (n - 1) - row * cols)
    } else if (dy < 0) {
      row = Math.max(0, row - 1)
      col = Math.min(col, (n - 1) - row * cols)
    } else if (dx > 0) {
      col = Math.min(cols - 1, col + 1)
    } else if (dx < 0) {
      col = Math.max(0, col - 1)
    }
    root.cursorIdx = Math.max(0, Math.min(n - 1, row * cols + col))
    gridView.ensureVisible(root.cursorIdx)
  }

  function openDetailAt(pos) {
    if (!root.db || !root.filtered.length) return
    pos = Math.max(0, Math.min(root.filtered.length - 1, Math.max(0, pos)))
    var full = root.filtered[pos]
    var e = root.db.entries[full]
    root.detailIdx = full
    root.detailPath = e.p
    root.detailVariants = Model.variantsOf(e)
    root.detailVariant = 0
    root.applyPhase = 0
    root.applyMsg = ""
  }

  function closeDetail() {
    root.detailIdx = -1
    root.detailPath = ""
    root.detailVariants = []
    root.applyPhase = 0
    root.applyMsg = ""
  }

  function detailNav(delta) {
    if (!root.db || !root.filtered.length) return
    var pos = root.filtered.indexOf(root.detailIdx)
    if (pos < 0) pos = 0
    pos = (pos + delta + root.filtered.length) % root.filtered.length
    root.openDetailAt(pos)
  }

  function cycleVariant(d) {
    var n = root.detailVariants.length
    if (!n) return
    root.detailVariant = ((root.detailVariant + d) % n + n) % n
  }

  function applySelected() {
    if (root.applyPhase === 1 || root.applyPhase === 2) return
    var vs = root.detailVariants
    if (!vs.length) return
    var v = vs[root.detailVariant % vs.length]
    if (!v.n || !root.baseOf() || !v.ct) {
      root.applyPhase = 4
      root.applyMsg = "missing theme data in index"
      return
    }
    root.applySlug = v.n
    root.applyPhase = 1
    root.applyMsg = "downloading " + v.n
    applyProc.command = ["/usr/bin/python3", "/home/gotar/.config/omarchy/plugins/gotar.omarchy-themes/bin/apply-theme.py",
                         v.n, root.baseOf(), v.ct, v.bg].slice()
    applyProc.running = true
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.hostWidget || root, direction)
    return false
  }

  onOpenedChanged: {
    if (opened) {
      root.startLoad(false)
      root.loadCurrentTheme()
    }
  }
  IpcHandler {
    target: "gotar.omarchy-themes"
    function open(): string { root.open(); return "ok" }
    function close(): string { root.close(); return "ok" }
    function toggle(): string { root.toggle(); return "ok" }
  }

  Component.onCompleted: {
    if (opened) {
      root.startLoad(false)
      root.loadCurrentTheme()
    }
  }

  // ---- processes ----------------------------------------------------------

  Process {
    id: fetchProc
    running: false
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.handleFetchOutput(String(text || ""))
    }
    onExited: function(exitCode) {
      if (exitCode !== 0 && root.phase === 0) {
        root.phase = 2
        root.phaseMsg = "index fetch failed (exit " + exitCode + ")"
      }
    }
  }

  Timer {
    id: fetchWatchdog
    interval: 180000
    repeat: false
    onTriggered: {
      if (root.phase === 0) {
        root.phase = 2
        root.phaseMsg = "fetch timed out \u2014 the 35 MB index is unreachable"
      }
    }
  }

  Timer {
    id: qTimer
    interval: 150
    repeat: false
    onTriggered: root.refreshFilters()
  }

  Process {
    id: themeCurProc
    running: false
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.currentTheme = String(text || "").trim()
    }
  }

  Process {
    id: applyProc
    running: false
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: function(text) {
        try {
          var j = JSON.parse(String(text || "{}"))
          if (j && j.error) root.applyMsg = String(j.error)
        } catch (e) {}
      }
    }
    onExited: function(exitCode) {
      if (exitCode === 0) {
        root.applyPhase = 2
        root.applyMsg = "applying theme\u2026"
        themeSetProc.command = ["omarchy", "theme", "set", root.applySlug]
        themeSetProc.running = true
      } else {
        root.applyPhase = 4
        if (!root.applyMsg) root.applyMsg = "install failed"
      }
    }
  }

  Process {
    id: themeSetProc
    running: false
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: function(text) {
        var t = String(text || "").trim()
        if (t) root.applyMsg = t
      }
    }
    onExited: function(exitCode) {
      if (exitCode === 0) {
        root.applyPhase = 3
        root.applyMsg = "\u2713 " + root.applySlug + " applied"
        root.loadCurrentTheme()
      } else {
        root.applyPhase = 4
        if (!root.applyMsg) root.applyMsg = "omarchy theme set failed"
      }
    }
  }

  // ---- UI ------------------------------------------------------------------

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(780))
    contentHeight: panel.fittedContentHeight(Style.space(560))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: searchField.activeFocus
      onCloseRequested: {
        if (root.detailPath !== "") root.closeDetail()
        else root.close()
      }
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onMoveRequested: function(dx, dy) {
        if (root.detailPath !== "") {
          if (dx !== 0) root.detailNav(dx > 0 ? 1 : -1)
          else if (dy !== 0) root.cycleVariant(dy > 0 ? 1 : -1)
        } else if (root.phase === 1) {
          root.moveCursor(dx, dy)
        }
      }
      onActivateRequested: {
        if (root.detailPath !== "") root.applySelected()
        else if (root.phase === 1) root.openDetailAt(root.cursorIdx)
      }
      onDeleteRequested: root.resetFilters()
      onTextKey: function(t) {
        if (t === "/" && root.detailPath === "") searchField.forceActiveFocus()
        else if ((t === "r" || t === "R") && root.detailPath === "") root.startLoad(true)
      }

      // ============================ main browse view =======================
      Item {
        id: content
        anchors.fill: parent
        visible: root.phase === 1

        Item {
          id: headerRow
          anchors.left: parent.left
          anchors.leftMargin: Style.spacing.md
          anchors.top: parent.top
          anchors.topMargin: Style.spacing.md
          anchors.right: parent.right
          anchors.rightMargin: Style.spacing.md
          height: Style.space(30)

          Text {
            id: slashText
            text: "/"
            color: root.dim
            font.family: root.mono
            font.pointSize: Style.font.body
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }
          Item {
            id: refreshBtn
            width: 24
            height: 24
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            Text {
              anchors.centerIn: parent
              text: "R"
              color: root.faint
              font.pointSize: Style.font.caption
              font.bold: true
            }
            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.startLoad(true)
            }
          }
          Item {
            id: resetBtn
            width: 24
            height: 24
            visible: root.hasActiveFilters
            anchors.right: refreshBtn.left
            anchors.rightMargin: Style.spacing.sm
            anchors.verticalCenter: parent.verticalCenter
            Text {
              anchors.centerIn: parent
              text: "\u00d7"
              color: root.dim
              font.pointSize: Style.font.body
            }
            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.resetFilters()
            }
          }
          Text {
            id: countText
            text: root.filtered.length + " / " + (root.db ? root.db.count : 0)
            color: root.dim
            font.family: root.mono
            font.pointSize: Style.font.caption
            anchors.right: resetBtn.left
            anchors.rightMargin: Style.spacing.sm
            anchors.verticalCenter: parent.verticalCenter
          }
          TextField {
            id: searchField
            anchors.left: slashText.right
            anchors.leftMargin: Style.spacing.sm
            anchors.right: countText.left
            anchors.rightMargin: Style.spacing.sm
            anchors.verticalCenter: parent.verticalCenter
            leftPadding: 8
            rightPadding: 8
            topPadding: 4
            bottomPadding: 4
            color: root.fg
            font.family: root.mono
            font.pointSize: Style.font.body
            placeholderText: "search themes, palettes, tags\u2026"
            placeholderTextColor: root.faint
            background: BorderSurface {
              radius: 4
              borderSpec: searchField.activeFocus
                ? Border.flat(root.dim, 1)
                : Border.flat(Color.background, 1)
            }
            onTextChanged: root.setQuery(text)
            onAccepted: {
              root.openDetailAt(0)
              searchField.activeFocus = false
              keyCatcher.forceActiveFocus()
            }
            Keys.onEscapePressed: {
              searchField.text = ""
              root.setQuery("")
              searchField.activeFocus = false
              keyCatcher.forceActiveFocus()
            }
          }
        }

        Row {
          id: bodyRow
          anchors.left: parent.left
          anchors.leftMargin: Style.spacing.md
          anchors.right: parent.right
          anchors.rightMargin: Style.spacing.md
          anchors.top: headerRow.bottom
          anchors.topMargin: Style.spacing.md
          anchors.bottom: statusRow.top
          anchors.bottomMargin: Style.spacing.md
          spacing: Style.spacing.lg

          // ----------------------- filter rail ---------------------------
          Column {
            id: filterCol
            width: Style.space(150)
            spacing: Style.spacing.md

            Text {
              text: "TONE"
              color: root.faint
              font.family: root.mono
              font.pointSize: Style.font.caption
              font.bold: true
            }
            Repeater {
              model: Model.TONES
              delegate: Item {
                id: toneRow
                width: filterCol.width
                height: 22
                property string val: modelData
                property bool active: root.tone === val
                property int count: (root.facets.tone[val]) || 0
                Rectangle {
                  anchors.fill: parent
                  radius: 4
                  color: toneHover.contains
                    ? (active ? Style.selectedFill : Style.hoverFill)
                    : (active ? Style.selectedFill : "transparent")
                }
                Rectangle {
                  visible: val === "dark"
                  width: 8
                  height: 8
                  radius: 4
                  color: "#3b4261"
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.leftMargin: 7
                }
                Rectangle {
                  visible: val === "light"
                  width: 8
                  height: 8
                  radius: 4
                  color: "#d6dbef"
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.leftMargin: 7
                }
                Text {
                  text: val
                  color: active ? root.fg : root.dim
                  font.family: root.mono
                  font.pointSize: Style.font.caption
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.leftMargin: 20
                }
                Text {
                  text: String(count)
                  color: root.faint
                  font.family: root.mono
                  font.pointSize: Style.font.caption
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.right: parent.right
                  anchors.rightMargin: 7
                }
                MouseArea {
                  id: toneHover
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.toggleFacet("tone", val)
                }
              }
            }

            Text {
              text: "COLOR"
              color: root.faint
              font.family: root.mono
              font.pointSize: Style.font.caption
              font.bold: true
            }
            Repeater {
              model: Model.COLOR_ORDER
              delegate: Item {
                id: colorRow
                width: filterCol.width
                height: 22
                property string val: modelData
                property bool active: root.color === val
                property int count: (root.facets.color[val]) || 0
                Rectangle {
                  anchors.fill: parent
                  radius: 4
                  color: colorHover.contains
                    ? (active ? Style.selectedFill : Style.hoverFill)
                    : (active ? Style.selectedFill : "transparent")
                }
                Rectangle {
                  width: 8
                  height: 8
                  radius: 4
                  color: {
                    if (val === "monochrome") return "#9aa0ab"
                    if (val === "red") return "#e74c5b"
                    if (val === "orange") return "#f5994f"
                    if (val === "yellow") return "#f0d869"
                    if (val === "green") return "#7bbf6f"
                    if (val === "cyan") return "#5ec3d0"
                    if (val === "blue") return "#6d8fee"
                    if (val === "purple") return "#a87cd9"
                    if (val === "pink") return "#e88abf"
                    return val
                  }
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.leftMargin: 7
                }
                Text {
                  text: val
                  color: active ? root.fg : root.dim
                  font.family: root.mono
                  font.pointSize: Style.font.caption
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.leftMargin: 20
                  elide: Text.ElideRight
                  width: filterCol.width - 66
                }
                Text {
                  text: String(count)
                  color: root.faint
                  font.family: root.mono
                  font.pointSize: Style.font.caption
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.right: parent.right
                  anchors.rightMargin: 7
                  width: 30
                  horizontalAlignment: Text.AlignRight
                }
                MouseArea {
                  id: colorHover
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.toggleFacet("color", val)
                }
              }
            }

            Text {
              text: "RESOLUTION"
              color: root.faint
              font.family: root.mono
              font.pointSize: Style.font.caption
              font.bold: true
            }
            Repeater {
              model: Model.RES_TIERS
              delegate: Item {
                id: resRow
                width: filterCol.width
                height: 22
                property string val: modelData
                property bool minActive: root.resMin === val
                property bool maxActive: root.resMax === val
                property int count: (root.facets.resMin[val]) || 0
                Text {
                  text: val
                  color: (minActive || maxActive) ? root.fg : root.dim
                  font.family: root.mono
                  font.pointSize: Style.font.caption
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.leftMargin: 7
                }
                Item {
                  width: 18
                  height: 22
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.leftMargin: Style.space(64)
                  Text {
                    anchors.centerIn: parent
                    text: "\u2265"
                    color: minActive ? root.fg : root.faint
                    font.family: root.mono
                    font.pointSize: Style.font.caption
                  }
                  MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleFacet("res-min", resRow.val)
                  }
                }
                Item {
                  width: 18
                  height: 22
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.leftMargin: Style.space(82)
                  Text {
                    anchors.centerIn: parent
                    text: "\u2264"
                    color: maxActive ? root.fg : root.faint
                    font.family: root.mono
                    font.pointSize: Style.font.caption
                  }
                  MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleFacet("res-max", resRow.val)
                  }
                }
                Text {
                  text: String(count)
                  color: root.faint
                  font.family: root.mono
                  font.pointSize: Style.font.caption
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.right: parent.right
                  anchors.rightMargin: 7
                  width: 30
                  horizontalAlignment: Text.AlignRight
                }
              }
            }
          }

          // ----------------------- wallpaper grid -------------------------
          Item {
            id: gridArea
            width: bodyRow.width - filterCol.width - bodyRow.spacing
            height: bodyRow.height

            Text {
              visible: root.filtered.length === 0
              anchors.centerIn: parent
              text: "no wallpapers match"
              color: root.dim
              font.family: root.mono
              font.pointSize: Style.font.body
            }

            GridView {
              id: gridView
              anchors.fill: parent
              anchors.margins: 1
              model: root.filtered
              focus: false
              clip: true
              boundsBehavior: Flickable.StopAtBounds
              interactive: true
              currentIndex: root.cursorIdx
              highlight: CursorSurface {
                hasCursor: true
                current: false
              }
              property real cw: Math.max(1,
                (width - (root.gridCols - 1) * Style.spacing.md) / root.gridCols)
              property real ch: cw * 9 / 16 + Style.space(26)
              cellWidth: cw
              cellHeight: ch
              delegate: Item {
                id: card
                width: gridView.cellWidth
                height: gridView.cellHeight
                required property var modelData
                required property int index
                property var entry: root.db && modelData !== undefined ? root.db.entries[modelData] : null

                Rectangle {
                  anchors.fill: parent
                  radius: 6
                  color: Color.background
                }
                Image {
                  anchors.fill: parent
                  anchors.bottomMargin: Style.space(26)
                  clip: true
                  fillMode: Image.PreserveAspectCrop
                  asynchronous: true
                  cache: false
                  source: card.entry ? root.url(card.entry.thumb) : ""
                  onSourceChanged: { if (status !== Image.Ready) opacity = 0 }
                  onStatusChanged: { opacity = (status === Image.Ready) ? 1 : 0 }
                }
                Column {
                  anchors.left: parent.left
                  anchors.leftMargin: 5
                  anchors.right: parent.right
                  anchors.rightMargin: 5
                  anchors.bottom: parent.bottom
                  anchors.bottomMargin: 4
                  spacing: 2
                  Text {
                    width: parent.width
                    text: card.entry ? (card.entry.t || card.entry.p) : ""
                    elide: Text.ElideRight
                    color: root.fg
                    font.family: root.mono
                    font.pointSize: Style.font.caption
                  }
                  Row {
                    spacing: 2
                    Repeater {
                      model: card.entry && card.entry.pal
                        ? Math.min(8, card.entry.pal.length) : 0
                      delegate: Rectangle {
                        required property int index
                        width: 6
                        height: 6
                        radius: 2
                        color: card.entry.pal[index]
                      }
                    }
                  }
                }
                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  hoverEnabled: true
                  onEntered: {
                    root.cursorIdx = index
                    gridView.ensureVisible(index)
                  }
                  onClicked: root.openDetailAt(index)
                }
              }
            }
          }
        }

        // ----------------------- status row -------------------------------
        Row {
          id: statusRow
          anchors.left: parent.left
          anchors.leftMargin: Style.spacing.md
          anchors.right: parent.right
          anchors.rightMargin: Style.spacing.md
          anchors.bottom: parent.bottom
          anchors.bottomMargin: Style.spacing.md
          spacing: Style.spacing.sm

          Rectangle {
            width: Style.space(64)
            height: 18
            radius: 4
            color: Style.hoverFill
            anchors.verticalCenter: parent.verticalCenter
            Text {
              anchors.centerIn: parent
              text: root.modeLabel
              color: root.dim
              font.family: root.mono
              font.pointSize: Style.font.caption
            }
          }
          Repeater {
            model: root.crumbs
            delegate: Rectangle {
              width: crumbText.implicitWidth + 26
              height: 18
              radius: 9
              color: Style.hoverFill
              property var crumb: modelData
              Text {
                id: crumbText
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 8
                text: crumb.label
                color: root.dim
                font.family: root.mono
                font.pointSize: Style.font.caption
              }
              Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.right: parent.right
                anchors.rightMargin: 8
                text: "\u00d7"
                color: root.faint
                font.pointSize: Style.font.caption
              }
              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.clearCrumb(crumb.key)
              }
            }
          }
          Item { width: 1 }
          Text {
            text: "arrows move \u00b7 enter view \u00b7 / search \u00b7 x reset \u00b7 r refetch"
            color: root.faint
            font.family: root.mono
            font.pointSize: Style.font.caption
            anchors.verticalCenter: parent.verticalCenter
          }
        }
      }

      // ============================ loading / error ========================
      Item {
        id: stateOverlay
        anchors.fill: parent
        visible: root.phase !== 1
        Column {
          anchors.centerIn: parent
          spacing: Style.spacing.md
          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.phase === 0 ? "LOADING INDEX" : "INDEX UNAVAILABLE"
            color: root.dim
            font.family: root.mono
            font.bold: true
            font.pointSize: Style.font.body
          }
          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            width: Style.space(420)
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            text: root.phaseMsg
              || (root.phase === 0
                ? "first run downloads the 35 MB wallpaper index (once, then cached for 24h)"
                : "")
            color: root.faint
            font.family: root.mono
            font.pointSize: Style.font.caption
          }
          Item {
            width: Style.space(120)
            height: Style.space(28)
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.phase === 2
            Rectangle {
              anchors.fill: parent
              radius: 6
              color: Style.hoverFill
            }
            Text {
              anchors.centerIn: parent
              text: "RETRY"
              color: root.fg
              font.family: root.mono
              font.pointSize: Style.font.caption
              font.bold: true
            }
            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.startLoad(true)
            }
          }
        }
      }

      // ============================ detail / apply =========================
      Item {
        id: detail
        anchors.fill: parent
        visible: root.detailPath !== ""
        z: 10
        property var entry: root.detailIdx >= 0 ? root.entryAt(root.detailIdx) : null

        Rectangle {
          anchors.fill: parent
          color: Color.popups.background
        }

        Column {
          id: detailCol
          anchors.fill: parent
          anchors.margins: Style.spacing.lg
          spacing: Style.spacing.md

          Row {
            id: detailHeader
            width: parent.width
            spacing: Style.spacing.sm
            Item {
              width: 26
              height: 22
              Text {
                anchors.centerIn: parent
                text: "\u2190"
                color: root.dim
                font.family: root.mono
                font.pointSize: Style.font.body
              }
              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.closeDetail()
              }
            }
            Text {
              width: detailCol.width - Style.space(260)
              text: detail.entry ? (detail.entry.t || detail.entry.p) : ""
              elide: Text.ElideRight
              color: root.fg
              font.family: root.mono
              font.pointSize: Style.font.subtitle
              font.bold: true
              anchors.verticalCenter: parent.verticalCenter
            }
            Text {
              text: detail.entry
                ? (detail.entry.tone + " \u00b7 " + detail.entry.color
                   + " \u00b7 " + detail.entry.w + "\u00d7" + detail.entry.h)
                : ""
              color: root.dim
              font.family: root.mono
              font.pointSize: Style.font.caption
              anchors.verticalCenter: parent.verticalCenter
            }
          }

          Row {
            width: parent.width
            height: Math.max(Style.space(120),
              detailCol.height
              - detailHeader.implicitHeight
              - variantList.implicitHeight
              - detailStatus.implicitHeight
              - Style.spacing.md * 3)
            spacing: Style.spacing.lg

            Item {
              width: Math.floor(parent.width * 0.5)
              height: parent.height
              Rectangle {
                anchors.fill: parent
                radius: 8
                color: Color.background
                clip: true
                Image {
                  anchors.fill: parent
                  fillMode: Image.PreserveAspectCrop
                  asynchronous: true
                  cache: false
                  source: detail.entry ? root.url(detail.entry.med) : ""
                  onSourceChanged: { if (status !== Image.Ready) opacity = 0 }
                  onStatusChanged: { opacity = (status === Image.Ready) ? 1 : 0 }
                }
              }
            }
            Column {
              width: parent.width - Math.floor(parent.width * 0.5) - parent.spacing
              height: parent.height
              spacing: Style.spacing.md

              Text {
                text: "PALETTE"
                color: root.faint
                font.family: root.mono
                font.pointSize: Style.font.caption
                font.bold: true
              }
              Row {
                spacing: 3
                Repeater {
                  model: detail.entry && detail.entry.pal
                    ? Math.min(12, detail.entry.pal.length) : 0
                  delegate: Rectangle {
                    width: 12
                    height: 12
                    radius: 3
                    color: detail.entry.pal[index]
                  }
                }
              }
              Text {
                text: "TAGS"
                color: root.faint
                font.family: root.mono
                font.pointSize: Style.font.caption
                font.bold: true
              }
              Flow {
                width: parent.width
                spacing: 4
                Repeater {
                  model: detail.entry && detail.entry.tags ? detail.entry.tags : []
                  delegate: Rectangle {
                    width: tagText.implicitWidth + 14
                    height: 18
                    radius: 9
                    color: Style.hoverFill
                    Text {
                      id: tagText
                      anchors.verticalCenter: parent.verticalCenter
                      anchors.left: parent.left
                      anchors.leftMargin: 7
                      text: modelData
                      color: root.dim
                      font.family: root.mono
                      font.pointSize: Style.font.caption
                    }
                  }
                }
              }
              Item { width: 1; height: 1 }
            }
          }

          Column {
            id: variantList
            width: parent.width
            spacing: 2
            Text {
              text: "ONE-CLICK APPLY"
              color: root.faint
              font.family: root.mono
              font.pointSize: Style.font.caption
              font.bold: true
            }
            Repeater {
              model: root.detailVariants
              delegate: Row {
                id: vrow
                width: variantList.width
                height: Style.space(30)
                property var v: modelData
                property bool sel: index === root.detailVariant
                property bool working:
                  (root.applyPhase === 1 || root.applyPhase === 2)
                  && root.applySlug === v.n
                property bool isActive:
                  root.currentTheme !== ""
                  && root.currentTheme.toLowerCase()
                  === Model.titleCase(v.n).toLowerCase()
                Rectangle {
                  anchors.fill: parent
                  radius: 6
                  color: sel ? Style.selectedFill : "transparent"
                }
                Rectangle {
                  width: 10
                  height: 10
                  radius: 5
                  color: v.hue
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.leftMargin: 10
                }
                Text {
                  width: Style.space(64)
                  text: v.label
                  color: sel ? root.fg : root.dim
                  font.family: root.mono
                  font.pointSize: Style.font.body
                  font.bold: sel
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.leftMargin: 28
                }
                Row {
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.leftMargin: Style.space(100)
                  spacing: 0
                  Repeater {
                    model: v.c ? v.c.length : 0
                    delegate: Rectangle {
                      width: Style.space(10)
                      height: Style.space(14)
                      color: v.c[index]
                    }
                  }
                }
                Text {
                  visible: root.applyPhase === 3 && root.applySlug === v.n
                  text: "\u2713"
                  color: root.okC
                  font.pointSize: Style.font.body
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.right: applyBtn.left
                  anchors.rightMargin: 6
                }
                Item {
                  id: applyBtn
                  width: Style.space(76)
                  height: Style.space(22)
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.right: parent.right
                  anchors.rightMargin: 8
                  Rectangle {
                    anchors.fill: parent
                    radius: 4
                    color: vrow.working
                      ? Style.hoverFill
                      : (vrow.isActive ? "transparent" : Style.selectedFill)
                    border.color: vrow.isActive ? root.okC : "transparent"
                    border.width: vrow.isActive ? 1 : 0
                  }
                  Text {
                    anchors.centerIn: parent
                    text: vrow.working ? "apply\u2026" : (vrow.isActive ? "active" : "Apply")
                    color: vrow.working ? root.faint
                      : (vrow.isActive ? root.okC : root.fg)
                    font.family: root.mono
                    font.pointSize: Style.font.caption
                    font.bold: !vrow.working
                  }
                  MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    hoverEnabled: true
                    onClicked: {
                      root.detailVariant = index
                      root.applySelected()
                    }
                  }
                }
              }
            }
          }

          Text {
            id: detailStatus
            width: parent.width
            text: root.applyPhase === 0
              ? "\u2190 \u2192 wallpaper \u00b7 \u2191 \u2193 variant \u00b7 enter apply \u00b7 esc back"
              : root.applyMsg
            color: root.applyPhase === 3 ? root.okC
              : (root.applyPhase === 4 ? root.errC : root.faint)
            font.family: root.mono
            font.pointSize: Style.font.caption
          }
        }
      }
    }
  }
}
