"""文件行內編輯區；段落自動長高，整份文件使用單一捲動區。"""
import math
from PySide6.QtCore import Qt,Signal,QTimer,QEvent
from PySide6.QtWidgets import QScrollArea,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTextEdit,QFrame,QPushButton
from PySide6.QtGui import QTextCursor
from .summary_layout import document_blocks
from .language import traditional
from .summary_transfer import BlockHandle,read_blocks

HEADING_SECTIONS={'heading_chair':'chair','heading_tracked':'tracked','heading_new':'new',
    'heading_closed':'closed','heading_reports':'reports','heading_motions':'motions','heading_previous':'previous'}

class ParagraphEdit(QTextEdit):
    def __init__(self,text,kind,parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False);self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(3)
        size=20 if kind=='company' else 18 if kind=='title' else 14
        weight='600' if kind in ('company','title','heading','metadata') else '400'
        self.setStyleSheet(f'QTextEdit {{ background: white; border: 1px solid transparent; border-radius: 3px; font-size: {size}px; font-weight: {weight}; }} QTextEdit:hover {{ border-color: #dde5e8; }} QTextEdit:focus {{ border-color: #328675; background: #fcfefd; }}')
        self.setPlainText(text)
        if kind in ('company','title'):self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif kind=='recorder':self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.document().documentLayout().documentSizeChanged.connect(self.fit_height)
        self.fit_height()

    def fit_height(self,*args):
        height=max(28,math.ceil(self.document().size().height())+4)
        if height!=self.height():self.setFixedHeight(height)

    def resizeEvent(self,event):
        super().resizeEvent(event);self.fit_height()

    def wheelEvent(self,event):
        event.ignore()

    def focusOutEvent(self,event):
        super().focusOutEvent(event)
        value=traditional(self.toPlainText())
        if value!=self.toPlainText():
            cursor=self.textCursor();position=cursor.position();anchor=cursor.anchor();alignment=self.alignment()
            self.setPlainText(value);self.setAlignment(alignment)
            cursor=self.textCursor();limit=self.document().characterCount()-1
            cursor.setPosition(min(anchor,limit));cursor.setPosition(min(position,limit),QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)

class DocumentEditor(QScrollArea):
    edited=Signal(str,str,str)
    insert_requested=Signal(list,str,str)
    remove_requested=Signal(list)
    target_changed=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True);self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet('QScrollArea { background: white; border: 1px solid #dce3e9; border-radius: 6px; }')
        self.edits={};self.prefix_labels={};self.blocks=[];self._loading=False
        self.token='';self.active_section='chair';self.drop_targets={};self.remove_buttons={};self.heading_rows={}
        self.highlight=None;self.scroll_delta=0
        self.scroll_timer=QTimer(self);self.scroll_timer.setInterval(50)
        self.scroll_timer.timeout.connect(self.drag_scroll)
        self.content=QWidget();self.content.setStyleSheet('background: white;')
        self.flow=QVBoxLayout(self.content);self.flow.setContentsMargins(16,10,16,12);self.flow.setSpacing(3)
        self.setWidget(self.content)

    def set_project(self,project):
        self.clear_drop_hint();self.drop_targets={};self.remove_buttons={};self.heading_rows={}
        scroll=self.verticalScrollBar().value();self._loading=True
        while self.flow.count():
            item=self.flow.takeAt(0)
            if item.widget():
                item.widget().hide();item.widget().deleteLater()
        self.edits={};self.prefix_labels={};self.blocks=document_blocks(project)
        for block in self.blocks:
            row=QWidget();layout=QHBoxLayout(row);layout.setContentsMargins(0,0,0,0);layout.setSpacing(2)
            row.setObjectName('blockRow')
            if block.kind in ('item','subheading'):layout.setContentsMargins(22,0,0,0)
            if block.kind=='item':
                handle=BlockHandle(block.key,self.token,row);layout.addWidget(handle,0,Qt.AlignmentFlag.AlignTop)
            if block.prefix or block.kind=='item':
                prefix=QLabel(block.prefix);prefix.setAlignment(Qt.AlignmentFlag.AlignTop)
                prefix.setContentsMargins(0,6,0,0);prefix.setMinimumWidth(34)
                layout.addWidget(prefix)
                self.prefix_labels[block.key]=prefix
            edit=ParagraphEdit(block.text,block.kind)
            edit.setAccessibleName('收錄內容' if block.kind=='item' else block.text or block.key)
            edit.setPlaceholderText('輸入內容…')
            edit.textChanged.connect(lambda e=edit,b=block:self.on_edit(b,e))
            layout.addWidget(edit,1)
            if block.kind=='item':
                remove=QPushButton('移除');remove.setFixedWidth(48)
                remove.setStyleSheet('QPushButton { padding:2px; min-width:0; color:#6f7f88; border:none; background:transparent; } QPushButton:hover { color:#ad403c; background:#fceeed; }')
                remove.setToolTip('移出會議紀錄；原文與修改仍會保留')
                remove.clicked.connect(lambda checked=False,key=block.key:self.remove_requested.emit([key]))
                layout.addWidget(remove,0,Qt.AlignmentFlag.AlignTop);self.remove_buttons[block.key]=remove
            section=block.section or HEADING_SECTIONS.get(block.key)
            if section:
                if block.kind!='item':self.heading_rows[section]=row
                for target in (row,edit.viewport(),edit):
                    target.setAcceptDrops(True);target.installEventFilter(self)
                    self.drop_targets[target]=(section,block.key if block.kind=='item' else '',row)
                edit.setToolTip('可直接編輯；將左側段落拖到此處加入')
            else:
                edit.setAcceptDrops(False)
            self.flow.addWidget(row);self.edits[block.key]=edit
        self.flow.addStretch(1);self._loading=False
        self.mark_active()
        QTimer.singleShot(0,lambda:self.verticalScrollBar().setValue(scroll))

    def mark_active(self):
        for section,row in self.heading_rows.items():
            color='#358874' if section==self.active_section else 'transparent'
            row.setStyleSheet(f'QWidget#blockRow {{ border-left:3px solid {color}; }}')

    def clear_drop_hint(self):
        if self.highlight:
            self.highlight.setStyleSheet('');self.highlight=None
        self.scroll_timer.stop();self.scroll_delta=0
        self.mark_active()

    def drag_scroll(self):
        bar=self.verticalScrollBar();bar.setValue(bar.value()+self.scroll_delta)

    def eventFilter(self,watched,event):
        target=getattr(self,'drop_targets',{}).get(watched)
        if not target:return super().eventFilter(watched,event)
        section,before,row=target;kind=event.type()
        if kind in (QEvent.Type.FocusIn,QEvent.Type.MouseButtonPress):
            self.active_section=section;self.mark_active();self.target_changed.emit(section)
        if kind in (QEvent.Type.DragEnter,QEvent.Type.DragMove,QEvent.Type.Drop):
            ids=read_blocks(event.mimeData(),self.token)
            if not ids:event.ignore();return True
            event.acceptProposedAction()
            if kind==QEvent.Type.Drop:
                self.clear_drop_hint();self.active_section=section;self.target_changed.emit(section)
                # Let Qt finish dispatching the drop before replacing its target widgets.
                QTimer.singleShot(0,lambda:self.insert_requested.emit(ids,section,before))
            else:
                if self.highlight is not row:self.clear_drop_hint()
                self.highlight=row
                row.setStyleSheet('QWidget#blockRow { border-top:2px solid #208775; background:#edf8f3; }')
                y=watched.mapTo(self.viewport(),event.position().toPoint()).y()
                self.scroll_delta=-20 if y<55 else 20 if y>self.viewport().height()-55 else 0
                if self.scroll_delta:self.scroll_timer.start()
                else:self.scroll_timer.stop()
            return True
        if kind==QEvent.Type.DragLeave:self.clear_drop_hint();return True
        return super().eventFilter(watched,event)

    def on_edit(self,block,edit):
        if not self._loading:self.edited.emit(block.kind,block.key,edit.toPlainText())

    def toPlainText(self):
        return '\n'.join(b.prefix+self.edits[b.key].toPlainText() for b in self.blocks)

    def sync_prefixes(self,project):
        self.blocks=document_blocks(project)
        for block in self.blocks:
            if block.key in self.prefix_labels:self.prefix_labels[block.key].setText(block.prefix)

    def reveal(self,key):
        edit=self.edits.get(key)
        if edit:self.ensureWidgetVisible(edit,0,20)

    def closeEvent(self,event):
        self._loading=True;super().closeEvent(event)
