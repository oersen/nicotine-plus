# COPYRIGHT (C) 2020-2021 Nicotine+ Team
#
# GNU GENERAL PUBLIC LICENSE
#    Version 3, 29 June 2007
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import textwrap
import threading
import time

from ctypes import Structure, byref, sizeof

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk

from pynicotine.config import config
from pynicotine.gtkgui.widgets.theme import get_icon
from pynicotine.logfacility import log


class Notifications:

    def __init__(self, frame):

        self.frame = frame
        self.application = Gio.Application.get_default()

        if sys.platform == "win32":
            self.win_notification = WinNotify(self.frame.tray_icon)

    def add(self, location, user, room=None):

        item = room if location == "rooms" else user

        if self.frame.np.notifications.add_hilite_item(location, item):
            self.frame.tray_icon.set_image()

        if (Gtk.get_major_version() == 3 and config.sections["ui"]["urgencyhint"]
                and not self.frame.MainWindow.is_active()):
            self.frame.MainWindow.set_urgency_hint(True)

        self.set_title(user)

    def clear(self, location, user=None, room=None):

        item = room if location == "rooms" else user

        if self.frame.np.notifications.remove_hilite_item(location, item):
            self.set_title(item)
            self.frame.tray_icon.set_image()

    def set_title(self, user=None):

        app_name = GLib.get_application_name()

        if (not self.frame.np.notifications.chat_hilites["rooms"]
                and not self.frame.np.notifications.chat_hilites["private"]):
            # Reset Title
            self.frame.MainWindow.set_title(app_name)
            return

        if not config.sections["notifications"]["notification_window_title"]:
            return

        if self.frame.np.notifications.chat_hilites["private"]:
            # Private Chats have a higher priority
            user = self.frame.np.notifications.chat_hilites["private"][-1]

            self.frame.MainWindow.set_title(
                app_name + " - " + _("Private Message from %(user)s") % {'user': user}
            )

        elif self.frame.np.notifications.chat_hilites["rooms"]:
            # Allow for the possibility the username is not available
            room = self.frame.np.notifications.chat_hilites["rooms"][-1]

            if user is None:
                self.frame.MainWindow.set_title(
                    app_name + " - " + _("You've been mentioned in the %(room)s room") % {'room': room}
                )
            else:
                self.frame.MainWindow.set_title(
                    app_name + " - " + _("%(user)s mentioned you in the %(room)s room") % {'user': user, 'room': room}
                )

    def new_text_notification(self, message, title=None, priority=Gio.NotificationPriority.NORMAL):

        if title is None:
            title = GLib.get_application_name()

        try:
            if sys.platform == "win32":
                self.win_notification.notify(
                    title=title,
                    message=message
                )

                if config.sections["notifications"]["notification_popup_sound"]:
                    import winsound
                    winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)

                return

            notification_popup = Gio.Notification.new(title)
            notification_popup.set_body(message)

            icon = get_icon("notify")
            if icon:
                notification_popup.set_icon(icon)

            notification_popup.set_priority(priority)

            self.application.send_notification(None, notification_popup)

            if config.sections["notifications"]["notification_popup_sound"]:
                Gdk.beep()

        except Exception as error:
            log.add(_("Unable to show notification popup: %s"), str(error))


class WinNotify:
    """ Implements a Windows balloon tip for GtkStatusIcon """

    NIF_INFO = NIIF_NOSOUND = 0x10
    NIM_MODIFY = 1

    def __init__(self, tray_icon):

        from ctypes import windll
        from ctypes.wintypes import DWORD, HICON, HWND, UINT, WCHAR

        class NOTIFYICONDATA(Structure):
            _fields_ = [
                ("cbSize", DWORD),
                ("hWnd", HWND),
                ("uID", UINT),
                ("uFlags", UINT),
                ("uCallbackMessage", UINT),
                ("hIcon", HICON),
                ("szTip", WCHAR * 128),
                ("dwState", DWORD),
                ("dwStateMask", DWORD),
                ("szInfo", WCHAR * 256),
                ("uVersion", UINT),
                ("szInfoTitle", WCHAR * 64),
                ("dwInfoFlags", DWORD)
            ]

        self.tray_icon = tray_icon
        self.queue = []
        self.worker = None

        self.nid = NOTIFYICONDATA()
        self.nid.cbSize = sizeof(NOTIFYICONDATA)
        self.nid.hWnd = windll.user32.FindWindowW("gtkstatusicon-observer", None)
        self.nid.uFlags = self.NIF_INFO
        self.nid.dwInfoFlags = self.NIIF_NOSOUND

    def notify(self, **kwargs):

        self.queue.append(kwargs)

        if self.worker and self.worker.is_alive():
            return

        self.worker = threading.Thread(target=self.work)
        self.worker.name = "WinNotify"
        self.worker.daemon = True
        self.worker.start()

    def work(self):

        while self.queue:
            kwargs = self.queue.pop(0)
            self._notify(**kwargs)

    def _notify(self, title="", message="", timeout=10):

        from ctypes import windll
        has_tray_icon = config.sections["ui"]["trayicon"]

        if not has_tray_icon:
            # Tray icon was disabled by the user. Enable it temporarily to show a notification.
            self.tray_icon.show()

        self.nid.szInfoTitle = textwrap.shorten(title, width=63, placeholder="...")
        self.nid.szInfo = textwrap.shorten(message, width=255, placeholder="...")

        windll.shell32.Shell_NotifyIconW(self.NIM_MODIFY, byref(self.nid))
        time.sleep(timeout)

        if not has_tray_icon:
            self.tray_icon.hide()
