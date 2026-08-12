import sys
import json
import os
import re
import csv
import ctypes
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QPushButton,
                             QWidget, QTextEdit, QHeaderView, QHBoxLayout,
                             QMenu, QAction, QInputDialog, QDialog, 
                             QCalendarWidget, QStyledItemDelegate,
                             QAbstractItemView, QTabWidget, QComboBox, QMessageBox,
                             QFileDialog, QFrame)
from PyQt5.QtGui import (QDesktopServices, QTextCursor, QColor, QFont, 
                           QKeySequence, QTextCharFormat, QBrush, QTextListFormat,
                           QTextBlockFormat, QPalette)
from PyQt5.QtCore import QUrl, Qt, QDate

# Helper function to convert Qt Rich Text / HTML into clean plain text for CSV/Excel export
def html_to_clean_text(html_str):
    if not html_str or not isinstance(html_str, str):
        return ""
    
    text = html_str
    # 1. Strip out head and style blocks completely
    text = re.sub(r'<head.*?>.*?</head>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # 2. Convert HTML list items to visible bullet markers
    text = re.sub(r'<li[^>]*>', '• ', text)
    text = re.sub(r'</li>', '\n', text)

    # 3. Convert paragraph endings and line breaks to standard newlines
    text = re.sub(r'</p>|<br\s*/?>', '\n', text)

    # 4. Strip away all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # 5. Unescape common HTML entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

    # Strip trailing/leading empty space while preserving text linebreaks
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join([l for l in lines if l]).strip()

# Custom QTableWidgetItem for sorting dates while keeping empty items pinned to the bottom
class DateTableItem(QTableWidgetItem):
    def __init__(self, text=""):
        super().__init__(text)
        
    def __lt__(self, other):
        t1 = self.text().replace("▼", "").strip()
        t2 = other.text().replace("▼", "").strip()
        
        table = self.tableWidget()
        if table:
            sort_order = table.horizontalHeader().sortIndicatorOrder()
            if sort_order == Qt.DescendingOrder:
                v1 = t1 if t1 else "0000-00-00"
                v2 = t2 if t2 else "0000-00-00"
            else:
                v1 = t1 if t1 else "9999-99-99"
                v2 = t2 if t2 else "9999-99-99"
        else:
            v1 = t1 if t1 else "9999-99-99"
            v2 = t2 if t2 else "9999-99-99"
            
        return v1 < v2

# Custom Widget using a checkable button with square corners and a dark green checked interior
class CenteredCheckBox(QWidget):
    def __init__(self, parent=None, checked=False, on_change=None, read_only=False):
        super().__init__(parent)
        self.button = QPushButton()
        self.button.setCheckable(True)
        self.button.setChecked(checked)
        self.update_button_appearance(checked)
        
        if read_only:
            self.button.setEnabled(False)
            
        self.button.clicked.connect(self._on_clicked)
        
        layout = QHBoxLayout(self)
        layout.addWidget(self.button)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        
        self.on_change_callback = on_change

    def update_button_appearance(self, checked):
        if checked:
            self.button.setText("●")
            self.button.setStyleSheet("""
                QPushButton {
                    background-color: #14360a;
                    color: white;
                    border: 1px solid #092404;
                    border-radius: 0px;
                    font-size: 8px;
                    width: 15px;
                    height: 15px;
                }
            """)
        else:
            self.button.setText("")
            self.button.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff;
                    border: 1px solid #777777;
                    border-radius: 0px;
                    width: 15px;
                    height: 15px;
                }
                QPushButton:hover {
                    border: 1px solid #14360a;
                }
                QPushButton:disabled {
                    background-color: #e0e0e0;
                    border: 1px solid #aaaaaa;
                }
            """)

    def _on_clicked(self, checked):
        self.update_button_appearance(checked)
        if self.on_change_callback:
            self.on_change_callback(checked)

    def isChecked(self):
        return self.button.isChecked()
        
    def setChecked(self, checked):
        self.button.setChecked(checked)
        self.update_button_appearance(checked)

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
    def __init__(self, parent=None, initial_date=None, is_dark_mode=False):
        super().__init__(parent)
        self.setWindowTitle("Select Date")
        self.setFixedSize(400, 300)
        
        layout = QVBoxLayout(self)
        self.calendar = QCalendarWidget(self)
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setHorizontalHeaderFormat(QCalendarWidget.SingleLetterDayNames)
        
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e1e1e;
                    color: #e0e0e0;
                }
                QPushButton {
                    background-color: #333333;
                    color: #ffffff;
                    border: 1px solid #555555;
                    padding: 6px;
                }
                QPushButton:hover {
                    background-color: #444444;
                }
            """)
            
            self.calendar.setStyleSheet("""
                QCalendarWidget QWidget { 
                    background-color: #252526; 
                    color: #e0e0e0; 
                }
                QCalendarWidget QWidget#qt_calendar_navigationbar { 
                    background-color: #333333; 
                }
                QCalendarWidget QToolButton { 
                    color: #ffffff; 
                    background-color: #333333; 
                    border: none;
                    font-weight: bold;
                    padding-right: 14px;
                }
                QCalendarWidget QToolButton::menu-indicator {
                    subcontrol-origin: padding;
                    subcontrol-position: center right;
                    right: 2px;
                }
                QCalendarWidget QToolButton:hover { 
                    background-color: #444444; 
                }
                QCalendarWidget QMenu { 
                    background-color: #2b2b2b; 
                    color: #ffffff; 
                }
                QCalendarWidget QSpinBox { 
                    background-color: #333333; 
                    color: #ffffff; 
                }
                QCalendarWidget QTableView {
                    background-color: #1e1e1e;
                    color: #e0e0e0;
                    selection-background-color: #1976D2;
                    selection-color: #ffffff;
                    gridline-color: #444444;
                }
                QCalendarWidget QTableView QHeaderView::section {
                    background-color: #333333;
                    color: #ffffff;
                    border: 1px solid #444444;
                    padding: 2px;
                    font-weight: bold;
                }
            """)
            
            header_fmt = QTextCharFormat()
            header_fmt.setBackground(QBrush(QColor("#333333")))
            header_fmt.setForeground(QBrush(QColor("#ffffff")))
            header_fmt.setFontWeight(QFont.Bold)
            self.calendar.setHeaderTextFormat(header_fmt)
            
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f5f5f5;
                    color: #000000;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #000000;
                    border: 1px solid #cccccc;
                    padding: 6px;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                }
            """)
            self.calendar.setStyleSheet("")
            self.calendar.setHeaderTextFormat(QTextCharFormat())
        
        if initial_date and initial_date.isValid():
            self.calendar.setSelectedDate(initial_date)
            
        layout.addWidget(self.calendar)
        self.calendar.activated.connect(self.accept)
        
        select_btn = QPushButton("Select", self)
        select_btn.clicked.connect(self.accept)
        layout.addWidget(select_btn)

    def get_selected_date(self):
        return self.calendar.selectedDate().toString("yyyy-MM-dd")

# Delegate to trigger calendar on double clicking Date columns
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
                
        is_dark = self.app_ref.is_dark_mode if self.app_ref else False
        dlg = CalendarDialog(parent, initial_date, is_dark_mode=is_dark)
        if dlg.exec_() == QDialog.Accepted:
            selected_date = dlg.get_selected_date()
            index.model().setData(index, selected_date, Qt.EditRole)
            if self.app_ref:
                self.app_ref.refresh_row_style(index.row())
        return None

class HyperlinkTextEdit(QTextEdit):
    def __init__(self, text="", table_ref=None, read_only=False, is_dark_mode=False):
        super().__init__()
        self.table_ref = table_ref
        self.setAcceptRichText(True)
        self.setReadOnly(read_only)
        self.is_dark_mode = is_dark_mode
        
        # Override default Qt list indent width
        self.document().setIndentWidth(30)
        
        # Set custom tab stop distance to control the gap width after bullets
        self.setTabStopDistance(12)
        
        self.update_style_and_links(text)

    def update_style_and_links(self, text="", text_color=None):
        if not text_color:
            text_color = "#e0e0e0" if self.is_dark_mode else "#000000"
            
        link_color_hex = "#64b5f6" if self.is_dark_mode else "#0000ff"
        scroll_thumb_color = "#555555" if self.is_dark_mode else "#c1c1c1"
        scroll_thumb_hover = "#777777" if self.is_dark_mode else "#a8a8a8"

        self.setStyleSheet(f"""
            QTextEdit {{
                border: none; 
                background-color: transparent;
                color: {text_color};
                font-family: 'Segoe UI';
                font-size: 15px; 
                selection-background-color: #b0d0ff;
                selection-color: #000000;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 2px 0px 2px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {scroll_thumb_color};
                min-height: 15px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {scroll_thumb_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        
        if text:
            self.setHtml(text)
            
        # Natively traverse and force override text colors on the underlying Qt text fragments
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        
        block = self.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    
                    if fmt.isAnchor() or fmt.underlineStyle() != QTextCharFormat.NoUnderline:
                        fmt.setForeground(QColor(link_color_hex))
                    else:
                        fmt.setForeground(QColor(text_color))
                        
                    # Clear any baked-in background highlights from copy-pasting
                    fmt.clearBackground()
                    
                    temp_cursor = QTextCursor(self.document())
                    temp_cursor.setPosition(fragment.position())
                    temp_cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.KeepAnchor)
                    temp_cursor.setCharFormat(fmt)
                    
                it += 1
            block = block.next()
            
        cursor.endEditBlock()

    def remove_formatting(self):
        cursor = self.textCursor()
        has_selection = cursor.hasSelection()
        
        # If nothing is selected, apply to the entire document block
        if not has_selection:
            cursor.select(QTextCursor.Document)
            
        text_color = "#e0e0e0" if self.is_dark_mode else "#000000"
        link_color = "#64b5f6" if self.is_dark_mode else "#0000ff"
            
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        
        cursor.setPosition(start)
        cursor.beginEditBlock()
        
        while cursor.position() < end:
            cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
            fmt = cursor.charFormat()
            
            clean_fmt = QTextCharFormat()
            # Safely rebuild standard links and text formats while leaving block structure (lists) intact
            if fmt.isAnchor():
                clean_fmt.setAnchor(True)
                clean_fmt.setAnchorHref(fmt.anchorHref())
                clean_fmt.setFontUnderline(True)
                clean_fmt.setForeground(QColor(link_color))
            else:
                clean_fmt.setForeground(QColor(text_color))
                
            cursor.setCharFormat(clean_fmt)
            cursor.setPosition(cursor.position())
            
        cursor.endEditBlock()
        
        if not has_selection:
            cursor.clearSelection()
            self.setTextCursor(cursor)

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
                    link_color_hex = "#64b5f6" if self.is_dark_mode else "#0000ff"
                    return f'<a href="{url}" style="color: {link_color_hex};">{url}</a>'
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
            remove_fmt_action = QAction("Remove Formatting", self)
            remove_fmt_action.triggered.connect(self.remove_formatting)
            menu.addAction(remove_fmt_action)
            
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
            link_color_hex = "#64b5f6" if self.is_dark_mode else "#0000ff"
            html_link = f'<a href="{url}" style="color: {link_color_hex};">{display_text}</a>'
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
        self.is_dark_mode = False
        
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

        self.todo_tab = QWidget()
        self.archive_tab = QWidget()
        
        self.tabs.addTab(self.todo_tab, "To-Do")
        self.tabs.addTab(self.archive_tab, "Archive")

        self.setup_todo_tab()
        self.setup_archive_tab()

    def create_table(self, is_archive=False):
        table = QTableWidget(0, len(self.headers) + 1)
        table.setHorizontalHeaderLabels(self.headers + ["_OriginalOrder"])
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFrameShape(QFrame.NoFrame)  
        table.setColumnHidden(len(self.headers), True)
        
        table.sort_state = {3: 0, 4: 0}
        
        if is_archive:
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        else:
            # Require double-click to edit/open calendar on date cells, preventing single-click header interference
            table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        
        header.sectionClicked.connect(lambda idx, t=table: self.on_header_clicked(t, idx))
        
        table.setColumnWidth(0, 130) # Category
        table.setColumnWidth(1, 380) # Tasks/Subtasks
        table.setColumnWidth(2, 90)  # Priority
        table.setColumnWidth(3, 130) # Date Assigned
        table.setColumnWidth(4, 130) # Deadline?
        table.setColumnWidth(5, 110) # Completed?
        table.setColumnWidth(6, 350) # Updates/Comments

        return table

    def on_header_clicked(self, table, logicalIndex):
        if logicalIndex not in [3, 4]:
            table.horizontalHeader().setSortIndicatorShown(False)
            table.sort_state = {3: 0, 4: 0}
            table.sortItems(len(self.headers), Qt.AscendingOrder)
            return
            
        state = table.sort_state
        current_stage = state[logicalIndex]
        
        other_idx = 4 if logicalIndex == 3 else 3
        state[other_idx] = 0
        
        new_stage = (current_stage + 1) % 3
        state[logicalIndex] = new_stage
        
        header = table.horizontalHeader()
        
        if new_stage == 1:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(logicalIndex, Qt.AscendingOrder)
            table.sortItems(logicalIndex, Qt.AscendingOrder)
        elif new_stage == 2:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(logicalIndex, Qt.DescendingOrder)
            table.sortItems(logicalIndex, Qt.DescendingOrder)
        else:
            header.setSortIndicatorShown(False)
            table.sortItems(len(self.headers), Qt.AscendingOrder)

    def on_item_changed(self, item):
        self.refresh_row_style(item.row())

    def setup_todo_tab(self):
        layout = QVBoxLayout(self.todo_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        self.todo_table = self.create_table(is_archive=False)
        
        date_delegate = DateDelegate(self.todo_table, app_ref=self)
        self.todo_table.setItemDelegateForColumn(3, date_delegate)
        self.todo_table.setItemDelegateForColumn(4, date_delegate)
        
        self.todo_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.todo_table.customContextMenuRequested.connect(self.open_context_menu)
        
        self.todo_table.itemChanged.connect(self.on_item_changed)
        
        layout.addWidget(self.todo_table)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(10, 10, 10, 10)
        
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

        self.dark_mode_btn = QPushButton("Dark Mode")
        self.dark_mode_btn.setStyleSheet("padding: 8px;")
        self.dark_mode_btn.clicked.connect(self.toggle_dark_mode)
        btn_layout.addWidget(self.dark_mode_btn)

        # Stretch spacing to push Export and Backup buttons to far right
        btn_layout.addStretch()

        # Right-aligned export and backup buttons
        self.export_btn = QPushButton("Export to CSV")
        self.export_btn.setStyleSheet("padding: 8px; font-weight: bold; background-color: #e1bee7; color: #000000;")
        self.export_btn.setFixedWidth(120)
        self.export_btn.clicked.connect(self.export_to_csv)
        btn_layout.addWidget(self.export_btn)

        self.backup_btn = QPushButton("Save Back-up")
        self.backup_btn.setStyleSheet("padding: 8px; font-weight: bold; background-color: #bbdefb; color: #000000;")
        self.backup_btn.setFixedWidth(120)
        self.backup_btn.clicked.connect(self.save_backup)
        btn_layout.addWidget(self.backup_btn)

        layout.addLayout(btn_layout)

    def setup_archive_tab(self):
        layout = QVBoxLayout(self.archive_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        self.archive_table = self.create_table(is_archive=True)
        
        self.archive_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.archive_table.customContextMenuRequested.connect(self.open_context_menu)
        
        layout.addWidget(self.archive_table)

    def toggle_dark_mode(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()
        self.save_data()

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_theme()

    def apply_theme(self):
        header_color = "#388E3C" if self.is_dark_mode else "#6CBE45"
        archive_header = "#B71C1C" if self.is_dark_mode else "#D32F2F"
        bg_color = "#1e1e1e" if self.is_dark_mode else "#f5f5f5"
        text_color = "#e0e0e0" if self.is_dark_mode else "#000000"
        grid_color = "#444444" if self.is_dark_mode else "#a0a0a0"
        table_bg = "#252526" if self.is_dark_mode else "#ffffff"

        scroll_thumb_color = "#555555" if self.is_dark_mode else "#c1c1c1"
        scroll_thumb_hover = "#777777" if self.is_dark_mode else "#a8a8a8"

        # Tab specific colors for Light & Dark mode
        todo_tab_selected = "#2e6930" if self.is_dark_mode else "#c8e6c9"
        todo_tab_unselected = "#1b3e20" if self.is_dark_mode else "#e8f5e9"
        
        archive_tab_selected = "#7a2829" if self.is_dark_mode else "#ffcdd2"
        archive_tab_unselected = "#4a1c1d" if self.is_dark_mode else "#ffebee"

        tab_text = "#ffffff" if self.is_dark_mode else "#000000"

        # 1. Update Windows Native Title Bar Theme (only when window is visible)
        if sys.platform == "win32" and hasattr(ctypes, "windll") and self.isVisible():
            try:
                hwnd = int(self.winId())
                value = ctypes.c_int(1 if self.is_dark_mode else 0)
                res = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
                if res != 0:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass

        # 2. Main Window, Tab Widget, & Custom Tab Colors
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {bg_color};
                color: {text_color};
            }}
            QTabWidget::pane {{
                border: 1px solid {grid_color};
                background-color: {table_bg};
            }}
            QTabBar::tab {{
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
                min-width: 120px;
                border: 1px solid {grid_color};
                border-bottom: none;
            }}
            QTabBar::tab:first {{
                background-color: {todo_tab_unselected};
                color: {tab_text};
            }}
            QTabBar::tab:first:selected {{
                background-color: {todo_tab_selected};
                color: {tab_text};
            }}
            QTabBar::tab:last {{
                background-color: {archive_tab_unselected};
                color: {tab_text};
            }}
            QTabBar::tab:last:selected {{
                background-color: {archive_tab_selected};
                color: {tab_text};
            }}
        """)

        # 3. Table & Thin Scrollbar Styling
        table_style = f"""
            QTableCornerButton::section {{
                background-color: {header_color};
                border: 1px solid {grid_color};
            }}
            QHeaderView::section {{
                background-color: {header_color};
                color: white;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid {grid_color};
                padding: 6px;
            }}
            QTableWidget {{
                background-color: {table_bg};
                gridline-color: {grid_color};
                font-size: 14px;
                outline: 0;
                border: none;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 2px 0px 2px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {scroll_thumb_color};
                min-height: 15px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {scroll_thumb_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """

        archive_style = f"""
            QTableCornerButton::section {{
                background-color: {archive_header};
                border: 1px solid {grid_color};
            }}
            QHeaderView::section {{
                background-color: {archive_header};
                color: white;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid {grid_color};
                padding: 6px;
            }}
            QTableWidget {{
                background-color: {table_bg};
                gridline-color: {grid_color};
                font-size: 14px;
                outline: 0;
                border: none;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 2px 0px 2px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {scroll_thumb_color};
                min-height: 15px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {scroll_thumb_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """

        self.todo_table.setStyleSheet(table_style)
        self.archive_table.setStyleSheet(archive_style)

        # Force Qt style polish so headers render styled on startup
        for w in [self, self.todo_table, self.archive_table, self.todo_table.horizontalHeader(), self.archive_table.horizontalHeader()]:
            w.style().unpolish(w)
            w.style().polish(w)

        # 4. Update row background, text, and link colors
        for r in range(self.todo_table.rowCount()):
            self.refresh_row_style(r)
        for r in range(self.archive_table.rowCount()):
            self.refresh_row_style(r, is_archive=True)

    def get_widget_row(self, table, widget):
        for r in range(table.rowCount()):
            for c in range(table.columnCount()):
                if table.cellWidget(r, c) == widget:
                    return r
        return -1

    def add_row(self, table, row_data=None, is_archive=False):
        table.blockSignals(True) 
        
        row = table.rowCount()
        table.insertRow(row)

        if not hasattr(table, 'row_counter'):
            table.row_counter = 0
            
        if row_data is None:
            row_data = {col: "" for col in self.headers}
            row_data["Completed?"] = False
            row_data["row_height"] = 90
            
        orig_order = row_data.get("_OriginalOrder", None)
        if orig_order is None:
            table.row_counter += 1
            orig_order = f"{table.row_counter:06d}"
        else:
            table.row_counter = max(table.row_counter, int(orig_order))
            
        row_data["_OriginalOrder"] = orig_order

        height = row_data.get("row_height", 90)
        table.setRowHeight(row, height)

        for col, header_name in enumerate(self.headers):
            if header_name in ["Date Assigned", "Deadline?"]:
                item = DateTableItem()
            else:
                item = QTableWidgetItem()
            
            if is_archive:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            
            if header_name in ["Tasks/Subtasks", "Updates/Comments"]:
                editor = HyperlinkTextEdit(row_data.get(header_name, ""), table_ref=table, read_only=is_archive, is_dark_mode=self.is_dark_mode)
                table.setItem(row, col, item)
                table.setCellWidget(row, col, editor)
            
            elif header_name == "Completed?":
                is_checked = row_data.get(header_name, False)
                cb_widget = CenteredCheckBox(
                    checked=is_checked, 
                    read_only=is_archive
                )
                if not is_archive:
                    cb_widget.on_change_callback = lambda state, w=cb_widget, t=table: self.refresh_row_style(self.get_widget_row(t, w))
                    
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
                
        hidden_item = QTableWidgetItem(orig_order)
        table.setItem(row, len(self.headers), hidden_item)

        table.blockSignals(False)
        
        if is_archive:
            self.refresh_row_style(row, is_archive=True)
        else:
            self.refresh_row_style(row)

    def archive_completed_rows(self):
        rows_to_archive = []
        
        for row in range(self.todo_table.rowCount() - 1, -1, -1):
            cb_widget = self.todo_table.cellWidget(row, self.headers.index("Completed?"))
            if isinstance(cb_widget, CenteredCheckBox) and cb_widget.isChecked():
                row_data = self.get_row_data(self.todo_table, row)
                if "_OriginalOrder" in row_data:
                    del row_data["_OriginalOrder"]
                rows_to_archive.append(row_data)
                self.todo_table.removeRow(row)

        for data in reversed(rows_to_archive):
            self.add_row(self.archive_table, data, is_archive=True)

    def refresh_row_style(self, row, is_archive=False):
        table = self.archive_table if is_archive else self.todo_table
        if row < 0 or row >= table.rowCount(): return
        
        table.blockSignals(True)
        
        try:
            if is_archive:
                bg_hex = "#2d2d2d" if self.is_dark_mode else "#ffffff"
                fg_hex = "#e0e0e0" if self.is_dark_mode else "#000000"
                bg_brush = QBrush(QColor(bg_hex))
                fg_brush = QBrush(QColor(fg_hex))
                
                for col in range(table.columnCount() - 1):
                    cell_item = table.item(row, col)
                    if cell_item:
                        cell_item.setBackground(bg_brush)
                        cell_item.setForeground(fg_brush)
                    
                    widget = table.cellWidget(row, col)
                    if isinstance(widget, HyperlinkTextEdit):
                        widget.is_dark_mode = self.is_dark_mode
                        widget.update_style_and_links(widget.toHtml(), text_color=fg_hex)
                    elif isinstance(widget, PriorityComboBox):
                        widget.setStyleSheet(f"""
                            QComboBox {{
                                border: none;
                                background-color: transparent;
                                color: {fg_hex};
                                font-family: 'Segoe UI';
                                font-size: 14px;
                            }}
                        """)
                return

            cb_widget = table.cellWidget(row, self.headers.index("Completed?"))
            is_completed = cb_widget.isChecked() if isinstance(cb_widget, CenteredCheckBox) else False

            bg_hex = "#2e5b1c" if (is_completed and self.is_dark_mode) else ("#3B7A24" if is_completed else ("#252526" if self.is_dark_mode else "#ffffff"))
            fg_hex = "#ffffff" if is_completed else ("#e0e0e0" if self.is_dark_mode else "#000000")
            caret_hex = "#a0dda0" if is_completed else ("#888888" if not self.is_dark_mode else "#aaaaaa")

            bg_brush = QBrush(QColor(bg_hex))
            fg_brush = QBrush(QColor(fg_hex))
            caret_brush = QBrush(QColor(caret_hex))

            today = QDate.currentDate()

            for col in range(table.columnCount() - 1):
                cell_item = table.item(row, col)
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
                                cell_item.setForeground(QBrush(QColor("#ff6b6b" if self.is_dark_mode else "#D32F2F"))) # Red
                                font.setBold(True)
                            elif days_diff == 1:
                                cell_item.setForeground(QBrush(QColor("#ffb74d" if self.is_dark_mode else "#FF8C00"))) # Amber/Orange
                                font.setBold(True)
                            else:
                                cell_item.setForeground(fg_brush)
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
                
                widget = table.cellWidget(row, col)
                
                if isinstance(widget, HyperlinkTextEdit):
                    widget.is_dark_mode = self.is_dark_mode
                    widget.update_style_and_links(widget.toHtml(), text_color=fg_hex)
                    
                elif isinstance(widget, PriorityComboBox):
                    widget.setStyleSheet(f"""
                        QComboBox {{
                            border: none;
                            background-color: transparent;
                            color: {fg_hex};
                            font-family: 'Segoe UI';
                            font-size: 14px;
                        }}
                        QComboBox QAbstractItemView {{
                            background-color: {"#333333" if self.is_dark_mode else "#ffffff"};
                            color: {fg_hex};
                            font-family: 'Segoe UI';
                            selection-background-color: #b0d0ff;
                        }}
                    """)
        finally:
            table.blockSignals(False)

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
        
    def get_all_rows_original_order(self, table):
        rows_data = []
        for r in range(table.rowCount()):
            data = self.get_row_data(table, r)
            hidden_item = table.item(r, len(self.headers))
            orig_order = int(hidden_item.text()) if hidden_item else 0
            rows_data.append((orig_order, data))
            
        rows_data.sort(key=lambda x: x[0])
        
        clean_rows = []
        for rd in rows_data:
            clean_rows.append(rd[1])
            
        return clean_rows

    def save_data(self):
        data = {
            "dark_mode": self.is_dark_mode,
            "todo": self.get_all_rows_original_order(self.todo_table),
            "archive": self.get_all_rows_original_order(self.archive_table)
        }

        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def save_backup(self):
        self.save_data()
        
        backup_dir = os.path.join(self.app_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_file = os.path.join(backup_dir, f"todo_data_backup_{timestamp}.json")
        
        data = {
            "dark_mode": self.is_dark_mode,
            "todo": self.get_all_rows_original_order(self.todo_table),
            "archive": self.get_all_rows_original_order(self.archive_table)
        }
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        QMessageBox.information(self, "Backup Saved", f"Backup created successfully:\n{backup_file}")

    def export_to_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to CSV", self.app_dir, "CSV Files (*.csv)")
        if not file_path:
            return

        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(self.headers + ["Status"])
            
            for row in range(self.todo_table.rowCount()):
                data = self.get_row_data(self.todo_table, row)
                row_vals = []
                for h in self.headers:
                    val = data.get(h, "")
                    if h in ["Tasks/Subtasks", "Updates/Comments"]:
                        val = html_to_clean_text(val)
                    row_vals.append(val)
                writer.writerow(row_vals + ["To-Do"])

            for row in range(self.archive_table.rowCount()):
                data = self.get_row_data(self.archive_table, row)
                row_vals = []
                for h in self.headers:
                    val = data.get(h, "")
                    if h in ["Tasks/Subtasks", "Updates/Comments"]:
                        val = html_to_clean_text(val)
                    row_vals.append(val)
                writer.writerow(row_vals + ["Archived"])

        QMessageBox.information(self, "Export Complete", f"Data exported successfully to CSV:\n{file_path}")

    def load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.is_dark_mode = data.get("dark_mode", False)
                        for row_data in data.get("todo", []):
                            self.add_row(self.todo_table, row_data, is_archive=False)
                        for row_data in data.get("archive", []):
                            self.add_row(self.archive_table, row_data, is_archive=True)
                    elif isinstance(data, list):
                        for row_data in data:
                            self.add_row(self.todo_table, row_data, is_archive=False)
                except json.JSONDecodeError:
                    self.add_row(self.todo_table, is_archive=False)
        else:
            self.add_row(self.todo_table, is_archive=False)

        self.apply_theme()

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