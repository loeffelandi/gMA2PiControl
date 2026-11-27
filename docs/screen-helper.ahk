#Requires AutoHotkey v2.0
#SingleInstance Force
Persistent
SetTitleMatchMode 2          ; Teilstring-Suche für Fenstertitel
SendMode "Input"

; ============================================================
;  grandMA2 onPC Screen-Helper
;  Lauscht auf UDP und sendet die Screen-Shortcuts als echte
;  PC-Tastendrücke:  Insert (an) -> Ctrl+Alt+F2..F6 -> Insert (aus)
;  Screen 1 holt nur das onPC-Fenster in den Vordergrund (kein Shortcut).
;
;  Der Pi (ma2pi) sendet Datagramme "screen 1" .. "screen 6".
; ============================================================

; ---- Konfiguration (bei Bedarf anpassen) ----
PORT       := 5010           ; nicht 5004/5005: das sind die Ports der RTP-MIDI-Session
ONPC_TITLE := "grandMA2"     ; Fenstertitel der onPC (Teilstring), nur für Screen 1.
LOG_FILE   := A_ScriptDir "\screen-helper.log"
; Hinweis: WinActivate NUR bei Screen 1 (das ist das Hauptfenster, sinnvoll zum
; Aufrufen). Bei Screen 2-6 KEIN WinActivate - das würde Screen 1 nach vorne
; holen und die anderen offenen Screens verdecken.

; ---- Winsock / UDP-Listener ----
WSAData := Buffer(408, 0)
if DllCall("ws2_32\WSAStartup", "UShort", 0x0202, "Ptr", WSAData.Ptr, "Int") != 0 {
    LogLine("WSAStartup fehlgeschlagen")
    ExitApp
}
sock := DllCall("ws2_32\socket", "Int", 2, "Int", 2, "Int", 17, "Ptr")  ; AF_INET, SOCK_DGRAM, UDP
if sock = -1 {
    LogLine("socket fehlgeschlagen")
    ExitApp
}
sa := Buffer(16, 0)
NumPut("UShort", 2, sa, 0)                 ; sin_family = AF_INET
NumPut("UShort", htons(PORT), sa, 2)       ; sin_port (Network Byte Order)
NumPut("UInt", 0, sa, 4)                   ; sin_addr = INADDR_ANY
if DllCall("ws2_32\bind", "Ptr", sock, "Ptr", sa.Ptr, "Int", 16, "Int") != 0 {
    LogLine("bind auf Port " PORT " fehlgeschlagen (schon belegt?)")
    ExitApp
}
; Non-blocking, damit der Timer die AHK-Message-Loop nicht blockiert
mode := Buffer(4, 0)
NumPut("UInt", 1, mode, 0)
DllCall("ws2_32\ioctlsocket", "Ptr", sock, "Int", 0x8004667E, "Ptr", mode.Ptr, "Int")  ; FIONBIO

recvBuf  := Buffer(1024, 0)
fromAddr := Buffer(16, 0)
fromLen  := Buffer(4, 0)
NumPut("Int", 16, fromLen, 0)

SetTimer(Poll, 25)
LogLine("Screen-Helper lauscht auf UDP " PORT)
TrayTip "Screen-Helper aktiv (UDP " PORT ")", "gMA2PiControl"

; ---- Manuelle Test-Hotkeys (ohne Pi) ----
F9::SendScreen(2)          ; Test: Screen 2 toggeln
F10::SendScreen(3)         ; Test: Screen 3 toggeln

Poll() {
    global sock, recvBuf, fromAddr, fromLen
    n := DllCall("ws2_32\recvfrom", "Ptr", sock, "Ptr", recvBuf.Ptr, "Int", 1024,
                 "Int", 0, "Ptr", fromAddr.Ptr, "Ptr", fromLen.Ptr, "Int")
    if n <= 0
        return
    ; Fremde Binärpakete (z. B. RTP-MIDI) ignorieren; RegExMatch bricht bei
    ; ungültigem Text mit einem PCRE-Fehler ab.
    Loop n {
        b := NumGet(recvBuf, A_Index - 1, "UChar")
        if (b < 0x20 || b > 0x7E) {
            LogLine("ignoriere " n " Byte ohne Textinhalt")
            return
        }
    }
    msg := StrGet(recvBuf.Ptr, n, "CP0")
    Handle(msg)
}

Handle(msg) {
    if RegExMatch(msg, "i)^screen\s+(\d+)$", &m) {
        n := Integer(m[1])
        if (n >= 1 && n <= 6) {
            LogLine("empfange '" msg "' -> Screen " n)
            SendScreen(n)
        }
    }
}

SendScreen(n) {
    global ONPC_TITLE
    ; Screen 1 ist das Hauptfenster: nur den Fokus setzen, keine Tasten senden.
    ; Screen 2-6: KEIN WinActivate (würde die anderen offenen Screens verdecken).
    if (n = 1) {
        if WinExist(ONPC_TITLE) {
            WinActivate
            LogLine("Screen 1 fokussiert")
        } else {
            LogLine("Screen 1: Fenster '" ONPC_TITLE "' nicht gefunden")
        }
        return
    }
    ; Screen 2-6, Struktur fest: Insert an -> Kombi -> Insert aus.
    Send "{Insert}"          ; Shortcut-Modus AN
    Sleep 300
    Send "^!{F" n "}"        ; Ctrl+Alt+Fn  (Screen n toggeln)
    Sleep 300
    Send "{Insert}"          ; Shortcut-Modus AUS
    LogLine("Screen " n " getoggelt (Insert -> F" n " -> Insert)")
}

htons(p) {
    return ((p & 0xFF) << 8) | ((p >> 8) & 0xFF)
}

LogLine(text) {
    global LOG_FILE
    try FileAppend FormatTime(, "yyyy-MM-dd HH:mm:ss") " " text "`n", LOG_FILE
}