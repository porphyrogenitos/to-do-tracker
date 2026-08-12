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
from PyQt5.QtCore import QUrl, Qt, QDate, QTimer

# ==========================================
# PRE-COMPILED REGEX FOR EFFICIENCY
# Compiling these at the module level prevents the engine from rebuilding 
# the pattern every time a cell is exported to CSV.
# ==========================================
RE_HEAD = re.compile(r'<head.*?>.*?</head>', flags=re.DOTALL | re.IGNORECASE)
RE_STYLE = re.compile(r'<style.*?>.*?</style>', flags=re.DOTALL | re.IGNORECASE)
RE_LI = re.compile(r'<li[^>]*>')
RE_LI_END = re.compile(r'</li>')
RE_P_BR = re.compile(r'</p>|<br\s*/?>')
RE_TAGS = re.compile(r'<[^>]+>')

def html_to_clean_text(html_str):
    """
    Strips HTML tags from PyQt's rich text format to produce clean plain text.
    This is specifically used to ensure CSV exports look normal while keeping bullet points.
    """
    if not html_str or not isinstance(html_str, str):
        return ""
    
    text = html_str
    # 1. Strip out head and style blocks completely (internal Qt formatting)
    text = RE_HEAD.sub('', text)
    text = RE_STYLE.sub('', text)

    # 2. Convert HTML list items to visible bullet markers for text output
    text = RE_LI.sub('• ', text)
    text = RE_LI_END.sub('\n', text)

    # 3. Convert paragraph endings and line breaks to standard newlines
    text = RE_P_BR.sub('\n', text)

    # 4. Strip away all remaining HTML tags
    text = RE_TAGS.sub('', text)

    # 5. Unescape common HTML entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

    # Strip trailing/leading empty space while preserving intentional text linebreaks
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join([l for l in lines if l]).strip()

# ==========================================
# CUSTOM WIDGETS & DELEGATES
# ==========================================

class DateTableItem(QTableWidgetItem):
    """
    Custom QTableWidgetItem for Dates. 
    It overrides the less-than operator (__lt__) so that sorting by date works chronologically,
    but forces empty date items (those just showing "▼") to always stay at the bottom of the list.
    """
    def __init__(self, text=""):
        super().__init__(text)
        
    def __lt__(self, other):
        # Strip the visual caret out before comparing
        t1 = self.text().replace("▼", "").strip()
        t2 = other.text().replace("▼", "").strip()
        
        table = self.tableWidget()
        if table:
            sort_order = table.horizontalHeader().sortIndicatorOrder()
            # If descending, treat blanks as lowest possible date (0000-00-00) to keep them at bottom.
            # If ascending, treat blanks as highest possible date (9999-99-99) to keep them at bottom.
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

class CenteredCheckBox(QWidget):
    """
    Uses a QPushButton instead of a QCheckBox to allow for custom square/circle styling 
    without dealing with QCheckBox's restrictive internal alignment and indicator limitations.
    """
    def __init__(self, parent=None, checked=False, on_change=None, read_only=False):
        super().__init__(parent)
        self.button = QPushButton()
        self.button.setCheckable(True)
        self.button.setChecked(checked)
        self.update_button_appearance(checked)
        
        if read_only:
            self.button.setEnabled(False)
            
        self.button.clicked.connect(self._on_clicked)
        
        # Center the button within the table cell
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
                QPushButton { background-color: #14360a; color: white; border: 1px solid #092404;
                              border-radius: 0px; font-size: 8px; width: 15px; height: 15px; }
            """)
        else:
            self.button.setText("")
            self.button.setStyleSheet("""
                QPushButton { background-color: #ffffff; border: 1px solid #777777; 
                              border-radius: 0px; width: 15px; height: 15px; }
                QPushButton:hover { border: 1px solid #14360a; }
                QPushButton:disabled { background-color: #e0e0e0; border: 1px solid #aaaaaa; }
            """)

    def _on_clicked(self, checked):
        self.update_button_appearance(checked)
        if self.on_change_callback:
            self.on_change_callback(checked)

    def isChecked(self): return self.button.isChecked()
    def setChecked(self, checked):
        self.button.setChecked(checked)
        self.update_button_appearance(checked)

class PriorityComboBox(QComboBox):
    """A frameless combobox designed to blend into the table row seamlessly."""
    def __init__(self, parent=None, read_only=False):
        super().__init__(parent)
        self.addItems(["", "Low", "Medium", "High"])
        if read_only: self.setEnabled(False)
        self.setStyleSheet("QComboBox { border: none; background-color: transparent; font-family: 'Segoe UI'; }")

class CalendarDialog(QDialog):
    """
    A standalone dialog window containing a QCalendarWidget. 
    Provides explicit dark mode styling to ensure it matches the rest of the application.
    """
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
            # Verbose stylesheet to force dark mode across all calendar sub-components
            self.setStyleSheet("""
                QDialog { background-color: #1e1e1e; color: #e0e0e0; }
                QPushButton { background-color: #333333; color: #ffffff; border: 1px solid #555555; padding: 6px; }
                QPushButton:hover { background-color: #444444; }
            """)
            self.calendar.setStyleSheet("""
                QCalendarWidget QWidget { background-color: #252526; color: #e0e0e0; }
                QCalendarWidget QWidget#qt_calendar_navigationbar { background-color: #333333; }
                QCalendarWidget QToolButton { color: #ffffff; background-color: #333333; border: none; font-weight: bold; padding-right: 14px; }
                QCalendarWidget QToolButton::menu-indicator { subcontrol-origin: padding; subcontrol-position: center right; right: 2px; }
                QCalendarWidget QToolButton:hover { background-color: #444444; }
                QCalendarWidget QMenu { background-color: #2b2b2b; color: #ffffff; }
                QCalendarWidget QSpinBox { background-color: #333333; color: #ffffff; }
                QCalendarWidget QTableView { background-color: #1e1e1e; color: #e0e0e0; selection-background-color: #1976D2; selection-color: #ffffff; gridline-color: #444444; }
                QCalendarWidget QTableView QHeaderView::section { background-color: #333333; color: #ffffff; border: 1px solid #444444; padding: 2px; font-weight: bold; }
            """)
            
            header_fmt = QTextCharFormat()
            header_fmt.setBackground(QBrush(QColor("#333333")))
            header_fmt.setForeground(QBrush(QColor("#ffffff")))
            header_fmt.setFontWeight(QFont.Bold)
            self.calendar.setHeaderTextFormat(header_fmt)
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f5f5f5; color: #000000; }
                QPushButton { background-color: #e0e0e0; color: #000000; border: 1px solid #cccccc; padding: 6px; }
                QPushButton:hover { background-color: #d0d0d0; }
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

class DateDelegate(QStyledItemDelegate):
    """
    Delegate attached to Date columns. When a user double clicks the cell, 
    it prevents normal text editing and instead opens the CalendarDialog.
    """
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
        # Return None so a default text editor doesn't appear in the cell
        return None

# ==========================================
# RICH TEXT EDITOR (CORE LOGIC)
# ==========================================

class HyperlinkTextEdit(QTextEdit):
    """
    Custom QTextEdit widget for Tasks and Comments columns.
    Handles:
    1. Automatic clickable hyperlinks.
    2. Seamless bullet creation shortcuts (Enter, Tab, Backspace, Shift+Tab, "* ").
    3. Custom context menus (Insert Link, Convert to Bullet).
    """
    def __init__(self, text="", table_ref=None, read_only=False, is_dark_mode=False):
        super().__init__()
        self.table_ref = table_ref
        self.setAcceptRichText(True)
        self.setReadOnly(read_only)
        self.is_dark_mode = is_dark_mode
        
        # Override default Qt list indent and tab stop to control gap width after bullets
        self.document().setIndentWidth(30)
        self.setTabStopDistance(12)
        
        self.update_style_and_links(text)

    def update_style_and_links(self, text="", text_color=None):
        """Re-applies styles and explicitly changes hyperlink colors to match light/dark themes."""
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
            QScrollBar:vertical {{ border: none; background: transparent; width: 6px; margin: 2px 0px 2px 0px; }}
            QScrollBar::handle:vertical {{ background: {scroll_thumb_color}; min-height: 15px; border-radius: 3px; }}
            QScrollBar::handle:vertical:hover {{ background: {scroll_thumb_hover}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ border: none; background: none; height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ border: none; background: none; }}
        """)
        
        if text:
            self.setHtml(text)
            
        # Iterate over all text blocks to re-tint anchors/links manually since Qt doesn't inherit link colors perfectly
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
                    fmt.clearBackground()
                    
                    temp_cursor = QTextCursor(self.document())
                    temp_cursor.setPosition(fragment.position())
                    temp_cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.KeepAnchor)
                    temp_cursor.setCharFormat(fmt)
                it += 1
            block = block.next()
        cursor.endEditBlock()

    def remove_formatting(self):
        """Strips bold/italic from the current selection, keeping hyperlinks intact."""
        cursor = self.textCursor()
        has_selection = cursor.hasSelection()
        if not has_selection:
            cursor.select(QTextCursor.Document)
            
        text_color = "#e0e0e0" if self.is_dark_mode else "#000000"
        link_color = "#64b5f6" if self.is_dark_mode else "#0000ff"
            
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.setPosition(start)
        
        cursor.beginEditBlock()
        while cursor.position() < end:
            cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
            fmt = cursor.charFormat()
            
            clean_fmt = QTextCharFormat()
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
        """Converts the current block to a bulleted list."""
        cursor = self.textCursor()
        list_fmt = QTextListFormat()
        
        if level == 1:
            list_fmt.setStyle(QTextListFormat.ListDisc)
            list_fmt.setIndent(1)
        else:
            list_fmt.setStyle(QTextListFormat.ListCircle)
            list_fmt.setIndent(2)
        
        cursor.createList(list_fmt)
        
        # Apply strict margins to control the spacing exactly (8px between paragraphs)
        block_fmt = cursor.blockFormat()
        block_fmt.setLeftMargin(0)
        block_fmt.setTopMargin(8) 
        cursor.setBlockFormat(block_fmt)
        
        cursor.movePosition(QTextCursor.StartOfBlock)
        if not cursor.block().text().startswith("\t"):
            cursor.insertText("\t")

    def keyPressEvent(self, event):
        if not self.isReadOnly():
            cursor = self.textCursor()
            
            # Standard keyboard shortcuts
            if event.matches(QKeySequence.Bold):
                self.toggle_bold()
                event.accept(); return
            elif event.matches(QKeySequence.Italic):
                self.toggle_italic()
                event.accept(); return

            current_list = cursor.currentList()

            # --- BACKSPACE HANDLER ---
            # If backspacing at the very start of a bullet line, remove the bullet 
            # and restore normal text formatting instead of awkwardly merging onto the previous line.
            if event.key() == Qt.Key_Backspace:
                if current_list and cursor.positionInBlock() <= 1:
                    block = cursor.block()
                    current_list.remove(block)
                    
                    block_fmt = cursor.blockFormat()
                    block_fmt.setObjectIndex(-1) # Disconnects from the list object
                    block_fmt.setIndent(0)
                    block_fmt.setLeftMargin(0)
                    block_fmt.setTopMargin(8) 
                    cursor.setBlockFormat(block_fmt)
                    
                    # Clean up the lingering tab character that pushed the text right
                    if block.text().startswith("\t"):
                        tc = QTextCursor(cursor)
                        tc.movePosition(QTextCursor.StartOfBlock)
                        tc.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
                        if tc.selectedText() == "\t":
                            tc.removeSelectedText()
                    event.accept()
                    return

            # --- ENTER / RETURN HANDLER ---
            # If pressing enter on an empty bullet line, exit the bullet list.
            # Otherwise, maintain paragraph spacing (8px).
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if current_list:
                    block = cursor.block()
                    if block.text().strip() == "":
                        if current_list.format().indent() > 1:
                            self.create_bullet_list(level=1)
                        else:
                            current_list.remove(block)
                            block_fmt = cursor.blockFormat()
                            block_fmt.setObjectIndex(-1)
                            block_fmt.setIndent(0)
                            block_fmt.setLeftMargin(0)
                            block_fmt.setTopMargin(8)
                            cursor.setBlockFormat(block_fmt)
                            
                            cursor.movePosition(QTextCursor.StartOfBlock)
                            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                            cursor.removeSelectedText()
                        event.accept()
                        return
                    else:
                        super().keyPressEvent(event)
                        new_cursor = self.textCursor()
                        block_fmt = new_cursor.blockFormat()
                        block_fmt.setTopMargin(8)
                        new_cursor.setBlockFormat(block_fmt)
                        if new_cursor.currentList() and not new_cursor.block().text().startswith("\t"):
                            new_cursor.insertText("\t")
                        return
                else:
                    super().keyPressEvent(event)
                    new_cursor = self.textCursor()
                    block_fmt = new_cursor.blockFormat()
                    block_fmt.setTopMargin(8) 
                    new_cursor.setBlockFormat(block_fmt)
                    return

            # --- TAB HANDLER ---
            # Tab indents to nested circle bullet.
            if event.key() == Qt.Key_Tab and not (event.modifiers() & Qt.ShiftModifier):
                if current_list and current_list.format().indent() < 2:
                    self.create_bullet_list(level=2)
                    event.accept()
                    return

            # --- SHIFT + TAB HANDLER ---
            # Shift+Tab outdents level 2 bullets to level 1, or removes level 1 bullets entirely.
            if event.key() == Qt.Key_Backtab or (event.key() == Qt.Key_Tab and (event.modifiers() & Qt.ShiftModifier)):
                if current_list:
                    current_indent = current_list.format().indent()
                    if current_indent > 1:
                        self.create_bullet_list(level=1)
                    else:
                        # Level 1 bullet: Remove list formatting completely
                        block = cursor.block()
                        current_list.remove(block)
                        
                        block_fmt = cursor.blockFormat()
                        block_fmt.setObjectIndex(-1)
                        block_fmt.setIndent(0)
                        block_fmt.setLeftMargin(0)
                        block_fmt.setTopMargin(8)
                        cursor.setBlockFormat(block_fmt)
                        
                        if block.text().startswith("\t"):
                            tc = QTextCursor(cursor)
                            tc.movePosition(QTextCursor.StartOfBlock)
                            tc.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
                            if tc.selectedText() == "\t":
                                tc.removeSelectedText()
                    event.accept()
                    return

            # --- ASTERISK-SPACE HANDLER ---
            # If user types '* ' at the start of a block, instantly convert the line to a bullet.
            if event.key() == Qt.Key_Space:
                cursor = self.textCursor()
                block = cursor.block()
                if cursor.positionInBlock() == 1 and block.text().startswith("*"):
                    tc = QTextCursor(cursor)
                    tc.movePosition(QTextCursor.StartOfBlock)
                    tc.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
                    tc.removeSelectedText() # Erase the asterisk
                    self.create_bullet_list(level=1)
                    event.accept()
                    return

        super().keyPressEvent(event)

    def toggle_bold(self):
        cursor = self.textCursor()
        fmt = QTextCharFormat()
        
        if cursor.hasSelection():
            # Check if majority/start of selection is bold to determine toggle state
            start, end = cursor.selectionStart(), cursor.selectionEnd()
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
            is_currently_bold = cursor.charFormat().fontWeight() == QFont.Bold
            fmt.setFontWeight(QFont.Normal if is_currently_bold else QFont.Bold)
            self.mergeCurrentCharFormat(fmt)

    def toggle_italic(self):
        cursor = self.textCursor()
        fmt = QTextCharFormat()
        
        if cursor.hasSelection():
            start, end = cursor.selectionStart(), cursor.selectionEnd()
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
            is_currently_italic = cursor.charFormat().fontItalic()
            fmt.setFontItalic(not is_currently_italic)
            self.mergeCurrentCharFormat(fmt)

    def insertFromMimeData(self, source):
        if self.isReadOnly(): return
        
        # Ensures pasted URLs are automatically wrapped in anchor tags
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
        # Allow single-clicking links to open them
        anchor = self.anchorAt(event.pos())
        if anchor:
            QDesktopServices.openUrl(QUrl(anchor))
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        click_cursor = self.cursorForPosition(event.pos())
        current_cursor = self.textCursor()
        
        # Preserve text selection if right-clicking INSIDE an active selection
        # Otherwise, move the cursor to where the user right-clicked
        if current_cursor.hasSelection():
            start, end = current_cursor.selectionStart(), current_cursor.selectionEnd()
            if not (start <= click_cursor.position() <= end):
                self.setTextCursor(click_cursor)
        else:
            self.setTextCursor(click_cursor)

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
            
            convert_bullet_action = QAction("Convert to Bullet", self)
            convert_bullet_action.triggered.connect(lambda: self.create_bullet_list(level=1))
            menu.addAction(convert_bullet_action)
            
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

# ==========================================
# MAIN APPLICATION LOGIC
# ==========================================

class TodoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("To-Do Tracker")
        self.is_dark_mode = False
        
        # PyInstaller packaging check for correct file paths
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
        
        # Calculate dynamic window width based on header requirements
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
        # Ensure styles render safely when switching back and forth
        self.tabs.currentChanged.connect(lambda idx: self.refresh_visible_rows())

        self.setup_todo_tab()
        self.setup_archive_tab()

    def create_table(self, is_archive=False):
        table = QTableWidget(0, len(self.headers) + 1)
        table.setHorizontalHeaderLabels(self.headers + ["_OriginalOrder"])
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFrameShape(QFrame.NoFrame)  
        table.setColumnHidden(len(self.headers), True) # Hidden tracking column for order
        
        table.sort_state = {3: 0, 4: 0} # 0=Default, 1=Ascending, 2=Descending
        
        if is_archive:
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        else:
            table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.sectionClicked.connect(lambda idx, t=table: self.on_header_clicked(t, idx))
        
        table.verticalScrollBar().valueChanged.connect(lambda val, t=table, arch=is_archive: self.on_table_scrolled(t, arch))
        
        # Fixed initial widths tailored to each column's specific utility
        table.setColumnWidth(0, 130) # Category
        table.setColumnWidth(1, 380) # Tasks/Subtasks
        table.setColumnWidth(2, 90)  # Priority
        table.setColumnWidth(3, 130) # Date Assigned
        table.setColumnWidth(4, 130) # Deadline?
        table.setColumnWidth(5, 110) # Completed?
        table.setColumnWidth(6, 350) # Updates/Comments

        return table

    def on_table_scrolled(self, table, is_archive):
        # Refresh logic is offloaded to scroll events to heavily boost UI performance
        current_active_table = self.archive_table if is_archive else self.todo_table
        if table != current_active_table:
            return
        self.refresh_visible_rows()

    def on_header_clicked(self, table, logicalIndex):
        # Only allow sorting on Date Assigned (3) and Deadline (4)
        if logicalIndex not in [3, 4]:
            table.horizontalHeader().setSortIndicatorShown(False)
            table.sort_state = {3: 0, 4: 0}
            table.sortItems(len(self.headers), Qt.AscendingOrder)
            return
            
        state = table.sort_state
        current_stage = state[logicalIndex]
        
        # Reset the *other* sortable column if we click this one
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
            table.sortItems(len(self.headers), Qt.AscendingOrder) # Revert to Original Order
            
        self.refresh_visible_rows()

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
        
        self.add_btn = QPushButton("+ Add New Task")
        self.add_btn.clicked.connect(lambda: self.add_row(self.todo_table, is_archive=False))
        btn_layout.addWidget(self.add_btn)

        self.archive_btn = QPushButton("Archive Completed")
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

        btn_layout.addStretch()

        self.export_btn = QPushButton("Export to CSV")
        self.export_btn.setFixedWidth(120)
        self.export_btn.clicked.connect(self.export_to_csv)
        btn_layout.addWidget(self.export_btn)

        self.backup_btn = QPushButton("Save Back-up")
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
        QTimer.singleShot(0, self.save_data)

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_theme()

    def apply_theme(self):
        """Builds CSS stylesheet blocks dynamically and forces theme redraw."""
        header_color = "#388E3C" if self.is_dark_mode else "#6CBE45"
        archive_header = "#B71C1C" if self.is_dark_mode else "#D32F2F"
        bg_color = "#1e1e1e" if self.is_dark_mode else "#f5f5f5"
        text_color = "#e0e0e0" if self.is_dark_mode else "#000000"
        grid_color = "#444444" if self.is_dark_mode else "#a0a0a0"
        table_bg = "#252526" if self.is_dark_mode else "#ffffff"

        scroll_thumb_color = "#555555" if self.is_dark_mode else "#c1c1c1"
        scroll_thumb_hover = "#777777" if self.is_dark_mode else "#a8a8a8"

        todo_tab_selected = "#2e6930" if self.is_dark_mode else "#c8e6c9"
        todo_tab_unselected = "#1b3e20" if self.is_dark_mode else "#e8f5e9"
        
        archive_tab_selected = "#7a2829" if self.is_dark_mode else "#ffcdd2"
        archive_tab_unselected = "#4a1c1d" if self.is_dark_mode else "#ffebee"

        tab_text = "#ffffff" if self.is_dark_mode else "#000000"

        # Action Button Styles (Dark Mode vs Light Mode)
        add_btn_style = "padding: 8px; font-weight: bold; background-color: #2d4f1e; color: #ffffff;" if self.is_dark_mode else "padding: 8px; font-weight: bold; background-color: #dcedc8; color: #000000;"
        archive_btn_style = "padding: 8px; font-weight: bold; background-color: #5c2427; color: #ffffff;" if self.is_dark_mode else "padding: 8px; font-weight: bold; background-color: #ffcdd2; color: #000000;"
        export_btn_style = "padding: 8px; font-weight: bold; background-color: #4a2859; color: #ffffff;" if self.is_dark_mode else "padding: 8px; font-weight: bold; background-color: #e1bee7; color: #000000;"
        backup_btn_style = "padding: 8px; font-weight: bold; background-color: #1a3c5e; color: #ffffff;" if self.is_dark_mode else "padding: 8px; font-weight: bold; background-color: #bbdefb; color: #000000;"

        self.add_btn.setStyleSheet(add_btn_style)
        self.archive_btn.setStyleSheet(archive_btn_style)
        self.export_btn.setStyleSheet(export_btn_style)
        self.backup_btn.setStyleSheet(backup_btn_style)

        # Windows-specific API hooks to forcefully theme the OS window title bar to dark mode
        if sys.platform == "win32" and hasattr(ctypes, "windll") and self.isVisible():
            try:
                hwnd = int(self.winId())
                value = ctypes.c_int(1 if self.is_dark_mode else 0)
                # 20 is DWMWA_USE_IMMERSIVE_DARK_MODE in Win 11, 19 in Win 10
                res = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
                if res != 0:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {bg_color}; color: {text_color}; }}
            QTabWidget::pane {{ border: 1px solid {grid_color}; background-color: {table_bg}; }}
            QTabBar::tab {{ padding: 10px 20px; font-weight: bold; font-size: 14px; min-width: 120px; border: 1px solid {grid_color}; border-bottom: none; }}
            QTabBar::tab:first {{ background-color: {todo_tab_unselected}; color: {tab_text}; }}
            QTabBar::tab:first:selected {{ background-color: {todo_tab_selected}; color: {tab_text}; }}
            QTabBar::tab:last {{ background-color: {archive_tab_unselected}; color: {tab_text}; }}
            QTabBar::tab:last:selected {{ background-color: {archive_tab_selected}; color: {tab_text}; }}
        """)

        table_style = f"""
            QTableCornerButton::section {{ background-color: {header_color}; border: 1px solid {grid_color}; }}
            QHeaderView::section {{ background-color: {header_color}; color: white; font-weight: bold; font-size: 13px; border: 1px solid {grid_color}; padding: 6px; }}
            QTableWidget {{ background-color: {table_bg}; gridline-color: {grid_color}; font-size: 14px; outline: 0; border: none; }}
            QScrollBar:vertical {{ border: none; background: transparent; width: 6px; margin: 2px 0px 2px 0px; }}
            QScrollBar::handle:vertical {{ background: {scroll_thumb_color}; min-height: 15px; border-radius: 3px; }}
            QScrollBar::handle:vertical:hover {{ background: {scroll_thumb_hover}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ border: none; background: none; height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ border: none; background: none; }}
        """

        self.todo_table.setStyleSheet(table_style)
        self.archive_table.setStyleSheet(table_style)

        # Force UI update queue for visual elements
        for w in [self, self.todo_table, self.archive_table, self.todo_table.horizontalHeader(), self.archive_table.horizontalHeader()]:
            w.style().unpolish(w)
            w.style().polish(w)

        # Temporarily disable table rendering while styles are applied row-by-row to prevent freezing
        self.todo_table.setUpdatesEnabled(False)
        self.archive_table.setUpdatesEnabled(False)
        try:
            for r in range(self.todo_table.rowCount()):
                self.refresh_row_style(r)
            for r in range(self.archive_table.rowCount()):
                self.refresh_row_style(r, is_archive=True)
        finally:
            self.todo_table.setUpdatesEnabled(True)
            self.archive_table.setUpdatesEnabled(True)

    def refresh_visible_rows(self):
        """Only updates row formatting for currently visible rows to keep scrolling highly responsive."""
        is_archive = (self.tabs.currentIndex() == 1)
        table = self.archive_table if is_archive else self.todo_table
        
        if table.rowCount() == 0: return

        viewport_height = table.viewport().height()
        top_row = table.rowAt(0)
        bottom_row = table.rowAt(viewport_height)

        if top_row == -1: top_row = 0
        if bottom_row == -1: bottom_row = table.rowCount() - 1

        # Calculate range buffer to smooth fast scrolling
        start_row = max(0, top_row - 3)
        end_row = min(table.rowCount() - 1, bottom_row + 3)

        for r in range(start_row, end_row + 1):
            self.refresh_row_style(r, is_archive=is_archive)

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
            
        # Defaults for a newly created row
        if row_data is None:
            row_data = {col: "" for col in self.headers}
            row_data["Completed?"] = False
            row_data["row_height"] = 90
            row_data["Date Assigned"] = QDate.currentDate().toString("yyyy-MM-dd")
            
        orig_order = row_data.get("_OriginalOrder", None)
        if orig_order is None:
            table.row_counter += 1
            orig_order = f"{table.row_counter:06d}"
        else:
            table.row_counter = max(table.row_counter, int(orig_order))
            
        row_data["_OriginalOrder"] = orig_order
        table.setRowHeight(row, row_data.get("row_height", 90))

        # Populate cell items and inject custom widgets where appropriate
        for col, header_name in enumerate(self.headers):
            item = DateTableItem() if header_name in ["Date Assigned", "Deadline?"] else QTableWidgetItem()
            if is_archive: item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            
            if header_name in ["Tasks/Subtasks", "Updates/Comments"]:
                editor = HyperlinkTextEdit(row_data.get(header_name, ""), table_ref=table, read_only=is_archive, is_dark_mode=self.is_dark_mode)
                table.setItem(row, col, item)
                table.setCellWidget(row, col, editor)
            
            elif header_name == "Completed?":
                cb_widget = CenteredCheckBox(checked=row_data.get(header_name, False), read_only=is_archive)
                if not is_archive:
                    cb_widget.on_change_callback = lambda state, w=cb_widget, t=table: self.refresh_row_style(self.get_widget_row(t, w))
                table.setItem(row, col, item)
                table.setCellWidget(row, col, cb_widget)

            elif header_name == "Priority":
                combo = PriorityComboBox(read_only=is_archive)
                idx = combo.findText(row_data.get(header_name, ""))
                if idx >= 0: combo.setCurrentIndex(idx)
                table.setItem(row, col, item)
                table.setCellWidget(row, col, combo)
            
            elif header_name in ["Date Assigned", "Deadline?"]:
                val = row_data.get(header_name, "").strip()
                item.setText("  ▼" if (not val and not is_archive) else val)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)

            else:
                item.setText(row_data.get(header_name, ""))
                table.setItem(row, col, item)
                
        # Hidden tracking column to revert chronological sorts
        table.setItem(row, len(self.headers), QTableWidgetItem(orig_order))
        table.blockSignals(False)
        self.refresh_row_style(row, is_archive=is_archive)

    def archive_completed_rows(self):
        """Moves fully checked off items from To-Do list over to the Archive tab."""
        rows_to_archive = []
        
        # Traverse rows in reverse so deletion doesn't mess up loop indexes
        for row in range(self.todo_table.rowCount() - 1, -1, -1):
            cb_widget = self.todo_table.cellWidget(row, self.headers.index("Completed?"))
            if isinstance(cb_widget, CenteredCheckBox) and cb_widget.isChecked():
                row_data = self.get_row_data(self.todo_table, row)
                if "_OriginalOrder" in row_data:
                    del row_data["_OriginalOrder"] # Assigns new order inside archive
                rows_to_archive.append(row_data)
                self.todo_table.removeRow(row)

        for data in reversed(rows_to_archive):
            self.add_row(self.archive_table, data, is_archive=True)

    def refresh_row_style(self, row, is_archive=False):
        """
        Dynamically colors the text and background of a given row based on:
        1. Light mode / Dark mode state.
        2. Whether the "Completed?" checkbox is checked (Green tint).
        3. How close the deadline is (Red/Orange warning colors).
        """
        table = self.archive_table if is_archive else self.todo_table
        if row < 0 or row >= table.rowCount(): return
        
        table.blockSignals(True)
        try:
            if is_archive:
                # Archive rows are static and greyed out
                bg_hex = "#2d2d2d" if self.is_dark_mode else "#ffffff"
                fg_hex = "#e0e0e0" if self.is_dark_mode else "#000000"
                bg_brush, fg_brush = QBrush(QColor(bg_hex)), QBrush(QColor(fg_hex))
                
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
                        widget.setStyleSheet(f"QComboBox {{ border: none; background-color: transparent; color: {fg_hex}; font-family: 'Segoe UI'; font-size: 14px; }}")
                return

            # Active table formatting logic
            cb_widget = table.cellWidget(row, self.headers.index("Completed?"))
            is_completed = cb_widget.isChecked() if isinstance(cb_widget, CenteredCheckBox) else False

            # Set background and text colors based on completion state and theme
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
                    
                    # Formatting logic for empty dropdowns
                    if header_name in ["Date Assigned", "Deadline?"] and "▼" in cell_item.text():
                        cell_item.setForeground(caret_brush)
                        font = cell_item.font(); font.setBold(False); cell_item.setFont(font)
                    
                    # Deadline proximity warnings (only applicable to incomplete tasks)
                    elif header_name == "Deadline?" and not is_completed:
                        date_str = cell_item.text().strip()
                        deadline_date = QDate.fromString(date_str, "yyyy-MM-dd")
                        font = cell_item.font()

                        if deadline_date.isValid():
                            days_diff = today.daysTo(deadline_date)
                            if days_diff <= 0:   # Overdue or Due Today (Red)
                                cell_item.setForeground(QBrush(QColor("#ff6b6b" if self.is_dark_mode else "#D32F2F")))
                                font.setBold(True)
                            elif days_diff == 1: # Due Tomorrow (Orange)
                                cell_item.setForeground(QBrush(QColor("#ffb74d" if self.is_dark_mode else "#FF8C00")))
                                font.setBold(True)
                            else:                # Due Later (Standard)
                                cell_item.setForeground(fg_brush)
                                font.setBold(False)
                        else:
                            cell_item.setForeground(fg_brush)
                            font.setBold(False)
                        cell_item.setFont(font)

                    else:
                        cell_item.setForeground(fg_brush)
                        font = cell_item.font(); font.setBold(False); cell_item.setFont(font)
                
                # Push style cascading into custom embedded widgets
                widget = table.cellWidget(row, col)
                if isinstance(widget, HyperlinkTextEdit):
                    widget.is_dark_mode = self.is_dark_mode
                    widget.update_style_and_links(widget.toHtml(), text_color=fg_hex)
                elif isinstance(widget, PriorityComboBox):
                    widget.setStyleSheet(f"""
                        QComboBox {{ border: none; background-color: transparent; color: {fg_hex}; font-family: 'Segoe UI'; font-size: 14px; }}
                        QComboBox QAbstractItemView {{ background-color: {"#333333" if self.is_dark_mode else "#ffffff"}; color: {fg_hex}; font-family: 'Segoe UI'; selection-background-color: #b0d0ff; }}
                    """)
        finally:
            table.blockSignals(False)

    def open_context_menu(self, position):
        table = self.sender()
        if not isinstance(table, QTableWidget): table = self.todo_table
        row = table.rowAt(position.y())
        if row < 0: return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #ffffff; border: 1px solid #555555; font-family: 'Segoe UI'; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #444444; color: #ffffff; }
        """)

        delete_action = QAction("Delete Row", self)
        menu.addAction(delete_action)

        action = menu.exec_(table.viewport().mapToGlobal(position))
        if action == delete_action: table.removeRow(row)

    def get_row_data(self, table, row):
        """Compiles row widget data into a clean JSON-friendly dictionary."""
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
        return [rd[1] for rd in rows_data]

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
        if not file_path: return

        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(self.headers + ["Status"])
            
            # Export active items
            for row in range(self.todo_table.rowCount()):
                data = self.get_row_data(self.todo_table, row)
                row_vals = []
                for h in self.headers:
                    val = data.get(h, "")
                    if h in ["Tasks/Subtasks", "Updates/Comments"]:
                        val = html_to_clean_text(val)
                    row_vals.append(val)
                writer.writerow(row_vals + ["To-Do"])

            # Export archived items
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