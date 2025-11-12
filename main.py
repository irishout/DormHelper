# main.py
import sys
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTableWidgetItem,
    QTreeWidgetItem,
    QPushButton,
    QMessageBox,
)
from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtGui import QStandardItemModel, QStandardItem

from window import Ui_MainWindow

import database


class DormHelper(QMainWindow):
    """Main application window wiring UI to the database layer.

    Implemented features:
    - Load and display news list + content
    - Submit maintenance requests and show them in the requests table
    - Load handbook tree and display selected content
    - Basic profile: show neighbors for a specified room (if any)
    """

    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # DB reference
        self.db = database

        # News model (QListView requires a model)
        self.news_model = QStandardItemModel(self)
        self.ui.newsList.setModel(self.news_model)

        # Connect signals
        self.ui.refreshNewsBtn.clicked.connect(self.load_news)
        # QListView emits clicked(index)
        self.ui.newsList.clicked.connect(self.on_news_selected)

        self.ui.submitRequestBtn.clicked.connect(self.submit_request)

        # Clear history button (placed inside the requests group box under the table)
        self.clearRequestsBtn = QPushButton("🧹 Очистить историю заявок")
        # place below the requests table inside the group box layout
        try:
            self.ui.verticalLayout_4.addWidget(self.clearRequestsBtn)
        except Exception:
            # fallback: add to main requests layout
            self.ui.verticalLayout_3.addWidget(self.clearRequestsBtn)
        self.clearRequestsBtn.clicked.connect(self.on_clear_requests_clicked)

        # Handbook tree click
        self.ui.handbookTree.itemClicked.connect(self.on_handbook_item_clicked)
        #database.add_handbook_item("Тест2", "Это еще одна тестовая информация")
        #database.delete_handbook_item("Тест2")

        self.ui.roomNumber.editingFinished.connect(self.load_requests)
        self.ui.studentRoom.editingFinished.connect(self.load_neighbors_for_room)

        # Confirm info button: allow user to add themselves to the students table / room
        self.confirmInfoBtn = QPushButton("✅ Подтвердить информацию")
        try:
            # try to insert into a form layout if present
            self.ui.formLayout_2.addRow(self.confirmInfoBtn)
        except Exception:
            # fallback: add to a likely vertical layout
            try:
                self.ui.verticalLayout_6.addWidget(self.confirmInfoBtn)
            except Exception:
                # last resort: add to main window (prevents crash if layout names differ)
                self.confirmInfoBtn.setParent(self)
        self.confirmInfoBtn.clicked.connect(self.on_confirm_info_clicked)

        # Initial loads
        self.load_news()
        self.load_requests()
        self.load_handbook()
        # show neighbors for any prefilled room
        self.load_neighbors_for_room()

    # -------------------- News --------------------
    def load_news(self) -> None:
        """Load latest news from DB and populate the list."""
        self.news_model.clear()
        try:
            items = self.db.get_news(limit=100)
        except Exception as e:
            self.statusBar().showMessage(f"Ошибка загрузки новостей: {e}")
            return

        for item in items:
            title = item.get("title") or "(без названия)"
            content = item.get("content") or ""
            nid = item.get("id")
            created = item.get("created_at") or ""
            display_text = f"{title} — {created}"
            it = QStandardItem(display_text)
            # store id and full content in user roles
            it.setData(nid, Qt.ItemDataRole.UserRole)
            it.setData(content, Qt.ItemDataRole.UserRole + 1)
            self.news_model.appendRow(it)

        self.statusBar().showMessage(f"Новости загружены: {len(items)}")

    def on_news_selected(self, index) -> None:
        """Show content of selected news item."""
        if not index.isValid():
            return
        item: QStandardItem = self.news_model.itemFromIndex(index)
        if not item:
            return
        content = item.data(Qt.ItemDataRole.UserRole + 1) or ""
        # Content may be plain text or HTML; display as HTML to keep formatting
        self.ui.newsContent.setHtml(content)

    # -------------------- Requests --------------------
    def submit_request(self) -> None:
        requester_name: Optional[str] = self.ui.studentName.text().strip() or None
        request_type = self.ui.requestType.currentText()
        description = self.ui.requestDescription.toPlainText().strip()
        room = self.ui.roomNumber.text().strip() or None

        if not description:
            self.statusBar().showMessage("Описание заявки пустое — заполните поле.")
            return

        try:
            req_id = self.db.add_request(requester_name, request_type, description, room)
        except Exception as e:
            self.statusBar().showMessage(f"Ошибка при отправке заявки: {e}")
            return

        self.statusBar().showMessage(f"Заявка отправлена (ID={req_id})")
        # clear description after submit
        self.ui.requestDescription.clear()
        # reload requests list
        self.load_requests()

    def load_requests(self) -> None:
        """Load recent requests and populate the requests table (simple view)."""
        try:
            rows = self.db.get_requests(limit=200)
        except Exception as e:
            self.statusBar().showMessage(f"Ошибка загрузки заявок: {e}")
            return

        table = self.ui.myRequestsTable
        table.setRowCount(0)
        for r in rows:
            row = table.rowCount()
            table.insertRow(row)
            # ID
            table.setItem(row, 0, QTableWidgetItem(str(r.get("id"))))
            # Type
            table.setItem(row, 1, QTableWidgetItem(r.get("request_type") or ""))
            # Status
            table.setItem(row, 2, QTableWidgetItem(r.get("status") or ""))
            # Date — display created_at or empty
            created = r.get("created_at") or ""
            table.setItem(row, 3, QTableWidgetItem(created))
            # description
            table.setItem(row, 4, QTableWidgetItem(r.get("description")))
            # room
            table.setItem(row, 5, QTableWidgetItem(r.get("room")))


        self.statusBar().showMessage(f"Заявки загружены: {len(rows)}")

    def on_clear_requests_clicked(self) -> None:
        """Ask for confirmation and clear all requests from DB."""
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы действительно хотите удалить всю историю заявок? Действие необратимо.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            deleted = self.db.clear_requests()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось очистить историю заявок: {e}")
            return

        self.load_requests()
        self.statusBar().showMessage(f"История заявок очищена ({deleted} записей удалено)")

    # -------------------- Handbook --------------------
    def load_handbook(self) -> None:
        """Load handbook root items and recursively populate the tree."""
        self.ui.handbookTree.clear()

        try:
            roots = self.db.get_handbook_children(None)
        except Exception as e:
            self.statusBar().showMessage(f"Ошибка загрузки справочника: {e}")
            return

        for node in roots:
            item = QTreeWidgetItem([node.get("title") or "(раздел)"])
            item.setData(0, Qt.ItemDataRole.UserRole, node.get("id"))
            item.setData(0, Qt.ItemDataRole.UserRole + 1, node.get("content") or "")
            self.ui.handbookTree.addTopLevelItem(item)
            self._load_handbook_children(item)

        self.statusBar().showMessage(f"Справочник загружен: {len(roots)} разделов")

    def _load_handbook_children(self, parent_item: QTreeWidgetItem) -> None:
        parent_id = parent_item.data(0, Qt.ItemDataRole.UserRole)
        try:
            children = self.db.get_handbook_children(parent_id)
        except Exception:
            children = []

        for node in children:
            it = QTreeWidgetItem([node.get("title") or "(пункт)"])
            it.setData(0, Qt.ItemDataRole.UserRole, node.get("id"))
            it.setData(0, Qt.ItemDataRole.UserRole + 1, node.get("content") or "")
            parent_item.addChild(it)
            # recursion
            self._load_handbook_children(it)

    def on_handbook_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        content = item.data(0, Qt.ItemDataRole.UserRole + 1) or ""
        self.ui.handbookContent.setHtml(content)

    # -------------------- Profile / Neighbors --------------------
    def load_neighbors_for_room(self) -> None:
        """Show students/neighbors for given room (basic behavior).

        Uses `find_students_by_room` to locate student(s) and then shows their names in the neighborsList.
        """
        room = self.ui.studentRoom.text().strip()
        list_widget = self.ui.neighborsList
        list_widget.clear()
        if not room:
            return

        try:
            students = self.db.find_students_by_room(room)
        except Exception as e:
            self.statusBar().showMessage(f"Ошибка поиска студентов: {e}")
            return

        # If there are students in the DB for the room, show their names as "neighbors" list
        for s in students:
            name = s.get("full_name") or "(без имени)"
            list_widget.addItem(name)

    def load_neighbors_for_room(self) -> None:
        """Show students/neighbors for given room (basic behavior).

        Uses `find_students_by_room` to locate student(s) and then shows their names in the neighborsList.
        """
        room = self.ui.studentRoom.text().strip()
        list_widget = self.ui.neighborsList
        list_widget.clear()
        if not room:
            return

        try:
            students = self.db.find_students_by_room(room)
        except Exception as e:
            self.statusBar().showMessage(f"Ошибка поиска студентов: {e}")
            return

        # If there are students in the DB for the room, show their names as "neighbors" list
        for s in students:
            name = s.get("full_name") or "(без имени)"
            list_widget.addItem(name)

    def on_confirm_info_clicked(self) -> None:
        """Confirm current user info: insert or update student record and refresh room occupants."""
        name = getattr(self.ui, "studentName", None)
        room = getattr(self.ui, "studentRoom", None)
        floor = getattr(self.ui, "studentFloor", None)
        if name is None or room is None:
            QMessageBox.warning(self, "Ошибка", "Элементы формы не найдены в интерфейсе.")
            return

        full_name = name.text().strip()
        room_text = room.text().strip()
        floor_text = floor.text().strip() if floor is not None else None

        if not full_name or not room_text:
            QMessageBox.warning(self, "Неполные данные", "Введите ФИО и номер комнаты перед подтверждением.")
            return

        try:
            existing = self.db.get_student_by_name_room(full_name, room_text)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось проверить данные в базе: {e}")
            return

        try:
            if existing:
                updated = self.db.update_student(existing["id"], full_name, room_text, floor_text)
                if updated:
                    QMessageBox.information(self, "Готово", "Информация подтверждена и обновлена.")
                    self.statusBar().showMessage("Информация о студенте обновлена в комнате.")
                else:
                    QMessageBox.information(self, "Готово", "Информация подтверждена.")
            else:
                sid = self.db.add_student(full_name, room_text, floor_text)
                QMessageBox.information(self, "Готово", "Информация подтверждена и добавлена в комнату.")
                self.statusBar().showMessage(f"Вы добавлены в список комнаты (ID={sid}).")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить информацию: {e}")
            return

        # refresh neighbors list to include the user
        self.load_neighbors_for_room()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DormHelper()
    window.show()
    sys.exit(app.exec())