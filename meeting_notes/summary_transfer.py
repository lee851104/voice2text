"""摘要段落的拖放資料與左側清單；只傳遞本專案的識別碼。"""
import json
from PySide6.QtCore import Qt, QMimeData, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QTableWidget, QPushButton, QApplication

MIME_TYPE='application/x-meeting-notes-blocks'

def block_mime(ids,token):
    mime=QMimeData()
    mime.setData(MIME_TYPE,json.dumps({'token':token,'ids':ids}).encode('utf-8'))
    return mime

def read_blocks(mime,token):
    if not mime.hasFormat(MIME_TYPE):return []
    try:
        data=json.loads(bytes(mime.data(MIME_TYPE)))
        if not isinstance(data,dict) or data.get('token')!=token:return []
        ids=data.get('ids')
        if not isinstance(ids,list) or not all(isinstance(i,str) for i in ids):return []
        return list(dict.fromkeys(ids))
    except (ValueError,TypeError,UnicodeError):return []

class SourceTable(QTableWidget):
    remove_requested=Signal(list)
    def __init__(self,parent=None):
        super().__init__(0,3,parent);self.token=''
        self.setDragEnabled(True);self.setAcceptDrops(True)
        self.setDragDropMode(QTableWidget.DragDropMode.DragDrop)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

    def selected_ids(self):
        return [self.item(row,1).data(Qt.ItemDataRole.UserRole)
                for row in sorted({i.row() for i in self.selectedItems()})]

    def mimeData(self,items):
        rows=sorted({i.row() for i in items})
        return block_mime([self.item(r,1).data(Qt.ItemDataRole.UserRole) for r in rows],self.token)

    def startDrag(self,actions):
        if not self.selected_ids():return
        drag=QDrag(self);drag.setMimeData(self.mimeData(self.selectedItems()))
        drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self,event):
        if read_blocks(event.mimeData(),self.token):event.acceptProposedAction()
        else:event.ignore()

    def dragMoveEvent(self,event):self.dragEnterEvent(event)

    def dropEvent(self,event):
        ids=read_blocks(event.mimeData(),self.token)
        if ids:event.acceptProposedAction();self.remove_requested.emit(ids)
        else:event.ignore()

class BlockHandle(QPushButton):
    def __init__(self,item_id,token,parent=None):
        super().__init__('≡',parent);self.item_id=item_id;self.token=token;self.origin=None
        self.setToolTip('拖曳整段：調整位置，或拖回左側移除')
        self.setAccessibleName('拖曳整段');self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFixedWidth(26)
        self.setStyleSheet('QPushButton { border:none; background:transparent; color:#76908b; padding:2px; min-width:0; }')

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.origin=event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.origin is not None and event.buttons()&Qt.MouseButton.LeftButton:
            if (event.position().toPoint()-self.origin).manhattanLength()>=QApplication.startDragDistance():
                self.origin=None;self.setDown(False)
                drag=QDrag(self);drag.setMimeData(block_mime([self.item_id],self.token));drag.exec(Qt.DropAction.CopyAction)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        self.origin=None;super().mouseReleaseEvent(event)
