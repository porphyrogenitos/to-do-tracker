import sys
import json
import os
import re
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QPushButton,
                             QWidget, QTextEdit, QHeaderView, QHBoxLayout,
                             QMenu, QAction, QInputDialog, QDialog, 
                             QCalendarWidget, QStyledItemDelegate, QCheckBox,
                             QAbstractItemView, QTabWidget, QComboBox, QMessageBox)
from PyQt5.QtGui import (QDesktopServices, QTextCursor, QColor, QFont, 
                           QKeySequence, QTextCharFormat, QBrush, QTextListFormat,
                           QTextBlockFormat)
from PyQt5.QtCore import QUrl, Qt, QDate

# Custom Widget to center the checkbox inside table cells
class CenteredCheckBox(QWidget):
    def __init__(self, parent=None, checked=False, on_change=None, read_only=False):
        super().__init__(parent)
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(checked)
        
        if read_only:
            self.checkbox.setEnabled(False) # Prevents user from toggling archive checks
            
        layout = QHBoxLayout(self)
        layout.addWidget(self.checkbox)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        
        if on_change and not read_only:
            self.checkbox.stateChanged.connect(on_change)
            
    def isChecked(self):
        return self.checkbox.isChecked()
        
    def setChecked(self, checked):
        self.checkbox.setChecked(checked)

# Custom Dropdown for Priority
class PriorityComboBox(QComboBox):
    def __init__(self, parent=None, read_only=False):
        super().__init__(parent)
        self.addItems(["", "Low", "Medium", "High"])
        
        if read_only:
            self.setEnabled(False)
            
        self.setStyleSheet("""
            QComboBox {
                border: none;
                background-color: transparent;
                font-family: 'Segoe UI';
            }
        """)

# Custom Calendar Popup Dialog Widget
class CalendarDialog(QDialog):
    def __init__(self, parent=None, initial_date=None):
        super().__init__(parent)
        self.setWindowTitle("Select Date")
        self.setFixedSize(300, 250)
        
        layout = QVBoxLayout(self)
        self.calendar = QCalendarWidget(self)
        self.calendar.setGridVisible(True)
        
        if initial_date and initial_date.isValid():
            self.calendar.setSelectedDate(initial_date)
            
        layout.addWidget(self.calendar)
        self.calendar.activated.connect(self.accept)
        
        select_btn = QPushButton("Select", self)
        select_btn.clicked.connect(self.accept)
        layout.addWidget(select_btn)

    def get_selected_date(self):
        return self.calendar.selectedDate().toString("yyyy-MM-dd")

# Delegate to trigger calendar on clicking Date columns
class DateDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, app_ref=None):
        super().__init__(parent)
        self.app_ref = app_ref

    def createEditor(self, parent, option, index):
        current_text = index.model().data(index, Qt.DisplayRole)
        
        if not current_text or "▼" in current_text:
            initial_date = QDate.currentDate()
        else:
            initial_date = QDate.fromString(current_text, "yyyy-MM-dd")
            if not initial_date.isValid():
                initial_date = QDate.currentDate()
                
        dlg = CalendarDialog(parent, initial_date)
        if dlg.exec_() == QDialog.Accepted:
            selected_date = dlg.get_selected_date()
            index.model().setData(index, selected_date, Qt.EditRole)
            if self.app_ref:
                self.app_ref.refresh_row_style(index.row())
        return None

class HyperlinkTextEdit(QTextEdit):
    def __init__(self, text="", table_ref=None, read_only=False):
        super().__init__()
        self.table_ref = table_ref
        self.setAcceptRichText(True)
        self.setReadOnly(read_only)
        
        # Override default Qt list indent width
        self.document().setIndentWidth(30)
        
        # Set custom tab stop distance to control the gap width after bullets
        self.setTabStopDistance(12)
        
        self.setStyleSheet("""
            QTextEdit {
                border: none; 
                background-color: transparent;
                color: inherit;
                font-family: 'Segoe UI';
                font-size: 15px; 
                selection-background-color: #b0d0ff;
                selection-color: #000000;
            }
        """)
        if text:
            self.setHtml(text)

    def create_bullet_list(self, level=1):
        cursor = self.textCursor()
        list_fmt = QTextListFormat()
        
        if level == 1:
            list_fmt.setStyle(QTextListFormat.ListDisc)
            list_fmt.setIndent(1)
        else:
            list_fmt.setStyle(QTextListFormat.ListCircle)
            list_fmt.setIndent(2)
        
        cursor.createList(list_fmt)
        
        block_fmt = cursor.blockFormat()
        block_fmt.setLeftMargin(0)
        cursor.setBlockFormat(block_fmt)
        
        if not cursor.block().text().startswith("\t"):
            cursor.insertText("\t")

    def keyPressEvent(self, event):
        if not self.isReadOnly():
            cursor = self.textCursor()
            
            # 1. Bold & Italic Shortcuts
            if event.matches(QKeySequence.Bold):
                self.toggle_bold()
                event.accept()
                return
            elif event.matches(QKeySequence.Italic):
                self.toggle_italic()
                event.accept()
                return

            current_list = cursor.currentList()

            # 2. Enter Key handling inside list / empty list
            if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                if current_list:
                    block = cursor.block()
                    if block.text().strip() == "":
                        current_indent = current_list.format().indent()
                        if current_indent > 1:
                            self.create_bullet_list(level=1)
                        else:
                            # Remove block from list, reset margins, and clear line text without deleting line break
                            current_list.remove(block)
                            block_fmt = cursor.blockFormat()
                            block_fmt.setObjectIndex(-1)
                            block_fmt.setIndent(0)
                            block_fmt.setLeftMargin(0)
                            cursor.setBlockFormat(block_fmt)
                            
                            cursor.movePosition(QTextCursor.StartOfBlock)
                            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                            cursor.removeSelectedText()
                        event.accept()
                        return
                    else:
                        super().keyPressEvent(event)
                        new_cursor = self.textCursor()
                        if new_cursor.currentList() and not new_cursor.block().text().startswith("\t"):
                            new_cursor.insertText("\t")
                        return

            # 3. Tab Key handling (Indent ONLY current item to Level 2 sub-bullet)
            if event.key() == Qt.Key_Tab and not (event.modifiers() & Qt.ShiftModifier):
                if current_list:
                    current_indent = current_list.format().indent()
                    if current_indent < 2:  # Cap at Level 2 max
                        self.create_bullet_list(level=2)
                    event.accept()
                    return

            # 4. Shift+Tab Key handling (Outdent ONLY current item back to Level 1)
            if event.key() == Qt.Key_Backtab or (event.key() == Qt.Key_Tab and (event.modifiers() & Qt.ShiftModifier)):
                if current_list:
                    current_indent = current_list.format().indent()
                    if current_indent > 1:
                        self.create_bullet_list(level=1)
                    event.accept()
                    return

            # 5. "* " trigger at the start of a line to enable bullet mode
            if event.key() == Qt.Key_Space:
                block_text = cursor.block().text()
                if block_text == "*":
                    cursor.movePosition(QTextCursor.StartOfBlock)
                    cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                    cursor.removeSelectedText()
                    
                    self.create_bullet_list(level=1)
                    event.accept()
                    return

        super().keyPressEvent(event)

    def toggle_bold(self):
        cursor = self.textCursor()
        fmt = QTextCharFormat()
        
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            
            is_bold = False
            tc = QTextCursor(cursor)
            tc.setPosition(start)
            while tc.position() < end:
                if tc.charFormat().fontWeight() == QFont.Bold:
                    is_bold = True
                    break
                if not tc.movePosition(QTextCursor.NextCharacter):
                    break
            
            fmt.setFontWeight(QFont.Normal if is_bold else QFont.Bold)
            cursor.mergeCharFormat(fmt)
        else:
            current_fmt = cursor.charFormat()
            is_currently_bold = current_fmt.fontWeight() == QFont.Bold
            fmt.setFontWeight(QFont.Normal if is_currently_bold else QFont.Bold)
            self.mergeCurrentCharFormat(fmt)

    def toggle_italic(self):
        cursor = self.textCursor()
        fmt = QTextCharFormat()
        
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            
            is_italic = False
            tc = QTextCursor(cursor)
            tc.setPosition(start)
            while tc.position() < end:
                if tc.charFormat().fontItalic():
                    is_italic = True
                    break
                if not tc.movePosition(QTextCursor.NextCharacter):
                    break
            
            fmt.setFontItalic(not is_italic)
            cursor.mergeCharFormat(fmt)
        else:
            current_fmt = cursor.charFormat()
            is_currently_italic = current_fmt.fontItalic()
            fmt.setFontItalic(not is_currently_italic)
            self.mergeCurrentCharFormat(fmt)

    def insertFromMimeData(self, source):
        if self.isReadOnly(): return
        
        if source.hasHtml():
            self.insertHtml(source.html())
        elif source.hasText():
            text = source.text()
            url_pattern = r'((?:https?://|onenote:)[^\s]+)'
            if re.search(url_pattern, text):
                def make_anchor(match):
                    url = match.group(0)
                    return f'<a href="{url}">{url}</a>'
                converted_html = re.sub(url_pattern, make_anchor, text).replace('\n', '<br>')
                self.insertHtml(converted_html)
            else:
                self.insertPlainText(text)
        else:
            super().insertFromMimeData(source)

    def mouseReleaseEvent(self, event):
        anchor = self.anchorAt(event.pos())
        if anchor:
            QDesktopServices.openUrl(QUrl(anchor))
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #ffffff; border: 1px solid #555555; font-family: 'Segoe UI'; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #444444; color: #ffffff; }
        """)
        
        menu.addSeparator()

        if not self.isReadOnly():
            insert_link_action = QAction("Insert Link...", self)
            insert_link_action.triggered.connect(self.prompt_insert_link)
            menu.addAction(insert_link_action)

        delete_action = QAction("Delete Row", self)
        delete_action.triggered.connect(self.delete_this_row)
        menu.addAction(delete_action)

        menu.exec_(event.globalPos())

    def prompt_insert_link(self):
        cursor = self.textCursor()
        selected_text = cursor.selectedText()
        url, ok = QInputDialog.getText(
            self, "Insert Link", "Enter URL (e.g. https://... or onenote:...):", text="https://"
        )
        if ok and url:
            display_text = selected_text if selected_text else url
            html_link = f'<a href="{url}">{display_text}</a>'
            cursor.insertHtml(html_link)

    def delete_this_row(self):
        if self.table_ref:
            for row in range(self.table_ref.rowCount()):
                for col in range(self.table_ref.columnCount()):
                    if self.table_ref.cellWidget(row, col) == self:
                        self.table_ref.removeRow(row)
                        return

class TodoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("To-Do Tracker")
        
        # Ensure json saves next to executable or script
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.data_file = os.path.join(app_dir, "todo_data.json")
        self.app_dir = app_dir
        
        self.headers = [
            "Category", "Tasks/Subtasks", "Priority", 
            "Date Assigned", "Deadline?", "Completed?", "Updates/Comments"
        ]

        self.init_ui()
        self.load_data()
        
        # Calculate exact width needed and trim excess padding
        header_width = self.todo_table.verticalHeader().width() if self.todo_table.verticalHeader().isVisible() else 30
        columns_width = sum(self.todo_table.columnWidth(i) for i in range(self.todo_table.columnCount()))
        
        required_width = columns_width + header_width + 25
        
        self.resize(required_width, 650)
        self.setMinimumWidth(required_width)

    def init_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        self.tabs.setStyleSheet("""
            QTabBar::tab {
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
                min-width: 120px; 
            }
        """)

        self.todo_tab = QWidget()
        self.archive_tab = QWidget()
        
        self.tabs.addTab(self.todo_tab, "To-Do")
        self.tabs.addTab(self.archive_tab, "Archive")

        self.setup_todo_tab()
        self.setup_archive_tab()

    def create_table(self, is_archive=False):
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(self.headers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        
        header_color = "#D32F2F" if is_archive else "#6CBE45"
        
        if is_archive:
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        else:
            table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        
        table.setStyleSheet(f"""
            QHeaderView::section {{
                background-color: {header_color};
                color: white;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #d3d3d3;
                padding: 6px;
            }}
            QTableWidget {{
                gridline-color: #a0a0a0;
                font-size: 14px;
                outline: 0;
            }}
            QTableWidget::item:selected, QTableWidget::item:focus {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
        """)

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        
        table.setColumnWidth(0, 130) # Category
        table.setColumnWidth(1, 380) # Tasks/Subtasks
        table.setColumnWidth(2, 90)  # Priority
        table.setColumnWidth(3, 130) # Date Assigned
        table.setColumnWidth(4, 130) # Deadline?
        table.setColumnWidth(5, 110) # Completed?
        table.setColumnWidth(6, 350) # Updates/Comments

        return table

    def on_item_changed(self, item):
        self.refresh_row_style(item.row())

    def setup_todo_tab(self):
        layout = QVBoxLayout(self.todo_tab)
        self.todo_table = self.create_table(is_archive=False)
        
        date_delegate = DateDelegate(self.todo_table, app_ref=self)
        self.todo_table.setItemDelegateForColumn(3, date_delegate)
        self.todo_table.setItemDelegateForColumn(4, date_delegate)
        
        self.todo_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.todo_table.customContextMenuRequested.connect(self.open_context_menu)
        
        self.todo_table.itemChanged.connect(self.on_item_changed)
        
        layout.addWidget(self.todo_table)

        btn_layout = QHBoxLayout()
        
        # Left-aligned action buttons
        self.add_btn = QPushButton("+ Add New Task")
        self.add_btn.setStyleSheet("padding: 8px; font-weight: bold; background-color: #dcedc8; color: #000000;")
        self.add_btn.clicked.connect(lambda: self.add_row(self.todo_table, is_archive=False))
        btn_layout.addWidget(self.add_btn)

        self.archive_btn = QPushButton("Archive Completed")
        self.archive_btn.setStyleSheet("padding: 8px; font-weight: bold; background-color: #ffcdd2; color: #000000;")
        self.archive_btn.clicked.connect(self.archive_completed_rows)
        btn_layout.addWidget(self.archive_btn)

        self.save_btn = QPushButton("Save Data")
        self.save_btn.setStyleSheet("padding: 8px;")
        self.save_btn.clicked.connect(self.save_data)
        btn_layout.addWidget(self.save_btn)

        # Stretch spacing to push Backup button to far right
        btn_layout.addStretch()

        # Right-aligned, narrower Backup button
        self.backup_btn = QPushButton("Save Back-up")
        self.backup_btn.setStyleSheet("padding: 8px; font-weight: bold; background-color: #bbdefb; color: #000000;")
        self.backup_btn.setFixedWidth(120)
        self.backup_btn.clicked.connect(self.save_backup)
        btn_layout.addWidget(self.backup_btn)

        layout.addLayout(btn_layout)

    def setup_archive_tab(self):
        layout = QVBoxLayout(self.archive_tab)
        self.archive_table = self.create_table(is_archive=True)
        
        self.archive_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.archive_table.customContextMenuRequested.connect(self.open_context_menu)
        
        layout.addWidget(self.archive_table)

    def add_row(self, table, row_data=None, is_archive=False):
        table.blockSignals(True) 
        
        row = table.rowCount()
        table.insertRow(row)

        if row_data is None:
            row_data = {col: "" for col in self.headers}
            row_data["Completed?"] = False
            row_data["row_height"] = 90

        height = row_data.get("row_height", 90)
        table.setRowHeight(row, height)

        for col, header_name in enumerate(self.headers):
            item = QTableWidgetItem()
            
            if is_archive:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            
            if header_name in ["Tasks/Subtasks", "Updates/Comments"]:
                editor = HyperlinkTextEdit(row_data.get(header_name, ""), table_ref=table, read_only=is_archive)
                table.setItem(row, col, item)
                table.setCellWidget(row, col, editor)
            
            elif header_name == "Completed?":
                is_checked = row_data.get(header_name, False)
                cb_widget = CenteredCheckBox(
                    checked=is_checked, 
                    on_change=(lambda state, r=row: self.refresh_row_style(r)) if not is_archive else None,
                    read_only=is_archive
                )
                table.setItem(row, col, item)
                table.setCellWidget(row, col, cb_widget)

            elif header_name == "Priority":
                combo = PriorityComboBox(read_only=is_archive)
                val = row_data.get(header_name, "")
                idx = combo.findText(val)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                table.setItem(row, col, item)
                table.setCellWidget(row, col, combo)
            
            elif header_name in ["Date Assigned", "Deadline?"]:
                val = row_data.get(header_name, "").strip()
                if not val and not is_archive:
                    item.setText("  ▼")
                else:
                    item.setText(val)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)

            else:
                item.setText(row_data.get(header_name, ""))
                table.setItem(row, col, item)

        table.blockSignals(False)
        
        if is_archive:
            for col in range(table.columnCount()):
                cell_item = table.item(row, col)
                if cell_item:
                    cell_item.setBackground(QBrush(QColor("#ffffff")))
                    cell_item.setForeground(QBrush(QColor("#000000")))
        else:
            self.refresh_row_style(row)

    def archive_completed_rows(self):
        rows_to_archive = []
        
        for row in range(self.todo_table.rowCount() - 1, -1, -1):
            cb_widget = self.todo_table.cellWidget(row, self.headers.index("Completed?"))
            if isinstance(cb_widget, CenteredCheckBox) and cb_widget.isChecked():
                row_data = self.get_row_data(self.todo_table, row)
                rows_to_archive.append(row_data)
                self.todo_table.removeRow(row)

        for data in reversed(rows_to_archive):
            self.add_row(self.archive_table, data, is_archive=True)

    def refresh_row_style(self, row):
        self.todo_table.blockSignals(True)
        
        try:
            cb_widget = self.todo_table.cellWidget(row, self.headers.index("Completed?"))
            is_completed = cb_widget.isChecked() if isinstance(cb_widget, CenteredCheckBox) else False

            bg_brush = QBrush(QColor("#3B7A24")) if is_completed else QBrush(QColor("#ffffff"))
            fg_brush = QBrush(QColor("#ffffff")) if is_completed else QBrush(QColor("#000000"))
            caret_brush = QBrush(QColor("#a0dda0")) if is_completed else QBrush(QColor("#888888"))

            today = QDate.currentDate()

            for col in range(self.todo_table.columnCount()):
                cell_item = self.todo_table.item(row, col)
                header_name = self.headers[col]

                if cell_item:
                    cell_item.setBackground(bg_brush)
                    
                    if header_name in ["Date Assigned", "Deadline?"] and "▼" in cell_item.text():
                        cell_item.setForeground(caret_brush)
                        font = cell_item.font()
                        font.setBold(False)
                        cell_item.setFont(font)
                    
                    elif header_name == "Deadline?" and not is_completed:
                        date_str = cell_item.text().strip()
                        deadline_date = QDate.fromString(date_str, "yyyy-MM-dd")
                        font = cell_item.font()

                        if deadline_date.isValid():
                            days_diff = today.daysTo(deadline_date)

                            if days_diff <= 0:
                                cell_item.setForeground(QBrush(QColor("#D32F2F"))) # Red
                                font.setBold(True)
                            elif days_diff == 1:
                                cell_item.setForeground(QBrush(QColor("#FF8C00"))) # Amber/Orange
                                font.setBold(True)
                            else:
                                cell_item.setForeground(QBrush(QColor("#000000"))) # Black
                                font.setBold(False)
                        else:
                            cell_item.setForeground(fg_brush)
                            font.setBold(False)
                        
                        cell_item.setFont(font)

                    else:
                        cell_item.setForeground(fg_brush)
                        font = cell_item.font()
                        font.setBold(False)
                        cell_item.setFont(font)
                
                widget = self.todo_table.cellWidget(row, col)
                
                if isinstance(widget, HyperlinkTextEdit):
                    text_color_css = "color: #ffffff;" if is_completed else "color: #000000;"
                    widget.setStyleSheet(f"""
                        QTextEdit {{
                            border: none; 
                            background-color: transparent;
                            {text_color_css}
                            font-family: 'Segoe UI';
                            font-size: 15px; 
                            selection-background-color: #b0d0ff;
                            selection-color: #000000;
                        }}
                    """)
                    
                elif isinstance(widget, PriorityComboBox):
                    text_color_css = "color: #ffffff;" if is_completed else "color: #000000;"
                    widget.setStyleSheet(f"""
                        QComboBox {{
                            border: none;
                            background-color: transparent;
                            {text_color_css}
                            font-family: 'Segoe UI';
                            font-size: 14px;
                        }}
                        QComboBox QAbstractItemView {{
                            background-color: #ffffff;
                            color: #000000;
                            font-family: 'Segoe UI';
                            selection-background-color: #b0d0ff;
                        }}
                    """)
        finally:
            self.todo_table.blockSignals(False)

    def open_context_menu(self, position):
        table = self.sender()
        if not isinstance(table, QTableWidget):
            table = self.todo_table

        row = table.rowAt(position.y())
        if row < 0:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #ffffff; border: 1px solid #555555; font-family: 'Segoe UI'; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #444444; color: #ffffff; }
        """)

        delete_action = QAction("Delete Row", self)
        menu.addAction(delete_action)

        action = menu.exec_(table.viewport().mapToGlobal(position))

        if action == delete_action:
            table.removeRow(row)

    def get_row_data(self, table, row):
        row_data = {"row_height": table.rowHeight(row)}
        for col, header_name in enumerate(self.headers):
            if header_name in ["Tasks/Subtasks", "Updates/Comments"]:
                widget = table.cellWidget(row, col)
                row_data[header_name] = widget.toHtml() if widget else ""
            
            elif header_name == "Completed?":
                widget = table.cellWidget(row, col)
                row_data[header_name] = widget.isChecked() if isinstance(widget, CenteredCheckBox) else False
                
            elif header_name == "Priority":
                widget = table.cellWidget(row, col)
                row_data[header_name] = widget.currentText() if isinstance(widget, PriorityComboBox) else ""
            
            elif header_name in ["Date Assigned", "Deadline?"]:
                item = table.item(row, col)
                val = item.text() if item else ""
                row_data[header_name] = "" if "▼" in val else val
            
            else:
                item = table.item(row, col)
                row_data[header_name] = item.text() if item else ""
        return row_data

    def save_data(self):
        data = {
            "todo": [],
            "archive": []
        }
        
        for row in range(self.todo_table.rowCount()):
            data["todo"].append(self.get_row_data(self.todo_table, row))
            
        for row in range(self.archive_table.rowCount()):
            data["archive"].append(self.get_row_data(self.archive_table, row))

        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    def save_backup(self):
        self.save_data()
        
        backup_dir = os.path.join(self.app_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_file = os.path.join(backup_dir, f"todo_data_backup_{timestamp}.json")
        
        data = {
            "todo": [self.get_row_data(self.todo_table, r) for r in range(self.todo_table.rowCount())],
            "archive": [self.get_row_data(self.archive_table, r) for r in range(self.archive_table.rowCount())]
        }
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
            
        QMessageBox.information(self, "Backup Saved", f"Backup created successfully:\n{backup_file}")

    def load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    if isinstance(data, list):
                        for row_data in data:
                            self.add_row(self.todo_table, row_data, is_archive=False)
                    elif isinstance(data, dict):
                        for row_data in data.get("todo", []):
                            self.add_row(self.todo_table, row_data, is_archive=False)
                        for row_data in data.get("archive", []):
                            self.add_row(self.archive_table, row_data, is_archive=True)
                except json.JSONDecodeError:
                    self.add_row(self.todo_table, is_archive=False)
        else:
            self.add_row(self.todo_table, is_archive=False)

    def closeEvent(self, event):
        self.save_data()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    window = TodoApp()
    window.show()
    sys.exit(app.exec_())