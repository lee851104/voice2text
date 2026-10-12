"""兩步驟：貼上摘要，再以整段拖放組成可直接編輯的文件。"""
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt,QThread,Signal,QTimer
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QPlainTextEdit,QLineEdit,QSplitter,QTableWidget,QTableWidgetItem,QHeaderView,
    QFileDialog,QMessageBox,QStackedWidget,QDialog,QFormLayout)
from . import __version__
from .theme import STYLE
from .language import traditional
from .summary_models import SummaryProject,SummaryItem,SECTIONS,parse_summary,save_summary,load_summary
from .summary_export import export_summary
from .summary_document_editor import DocumentEditor
from .summary_service import rewrite_selected,safe_error,DEFAULT_MODEL
from .summary_transfer import SourceTable

class RewriteJob(QThread):
    completed=Signal(object)
    failed=Signal(str)
    progress=Signal(str)
    def __init__(self,project,key,model,parent=None):
        super().__init__(parent)
        self.project=project.model_copy(deep=True);self.key=key;self.model=model
    def run(self):
        try:self.completed.emit(rewrite_selected(self.project,self.key,self.model,progress=self.progress.emit))
        except Exception as error:self.failed.emit(safe_error(error,self.key))
        finally:self.key=''

class SummaryWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project=SummaryProject();self.path=None;self.dirty=False;self._loading=False
        self.job=None;self.before_rewrite=None;self.rewritten_texts={}
        self.target_section='chair';self.session_token=uuid4().hex
        self.resize(1366,820);self.setMinimumSize(980,640)
        self.setStyleSheet(STYLE+'''
            QPushButton { padding:5px 11px; min-height:20px; }
            QPushButton#step { border:none; background:transparent; font-size:14px; padding:6px 12px; }
            QPushButton#step:checked { color:#176c58; background:#e1f0ea; font-weight:600; }
            QTableWidget::item { padding:5px; }
            QPlainTextEdit#source { padding:10px; font-size:15px; }
        ''')
        body=QWidget();self.setCentralWidget(body)
        layout=QVBoxLayout(body);layout.setContentsMargins(12,10,12,8);layout.setSpacing(7)
        top=QHBoxLayout();top.setSpacing(6)
        self.step1_button=self.button('1　貼上文字摘要',lambda:self.pages.setCurrentIndex(0))
        self.step2_button=self.button('2　勾選與編輯',self.go_review)
        for button in (self.step1_button,self.step2_button):button.setCheckable(True);button.setObjectName('step');top.addWidget(button)
        top.addStretch()
        self.new_button=self.button('新會議',self.new_project);top.addWidget(self.new_button)
        self.open_button=self.button('開啟',self.open_project);top.addWidget(self.open_button)
        self.save_button=self.button('儲存',self.save_project);top.addWidget(self.save_button)
        layout.addLayout(top)
        self.pages=QStackedWidget();layout.addWidget(self.pages,1)
        source_page=QWidget();source_layout=QVBoxLayout(source_page);source_layout.setContentsMargins(0,0,0,0);source_layout.setSpacing(7)
        self.source_input=QPlainTextEdit();self.source_input.setObjectName('source')
        self.source_input.setPlaceholderText('在此貼上 NotebookLM 的完整文字摘要。\n\n按「下一步」會先收錄全部內容，再勾選、拖曳或直接編輯。')
        self.source_input.textChanged.connect(self.source_changed);source_layout.addWidget(self.source_input,1)
        bar=QHBoxLayout();note=QLabel('預設在本機直接轉換，不需要金鑰。');note.setObjectName('muted');bar.addWidget(note);bar.addStretch()
        self.parse_button=self.button('下一步　→',self.go_review,True);bar.addWidget(self.parse_button);source_layout.addLayout(bar)
        self.pages.addWidget(source_page)
        review_page=QWidget();review_layout=QVBoxLayout(review_page);review_layout.setContentsMargins(0,0,0,0)
        self.splitter=QSplitter(Qt.Orientation.Horizontal);self.splitter.setHandleWidth(10)
        self.splitter.setChildrenCollapsible(False)
        list_panel=QWidget();left=QVBoxLayout(list_panel);left.setContentsMargins(0,0,0,0);left.setSpacing(6)
        selectbar=QHBoxLayout();selectbar.addWidget(QLabel('原始摘要'));selectbar.addStretch()
        hint=QLabel('勾選收錄 · 可拖曳');hint.setObjectName('muted');selectbar.addWidget(hint)
        self.select_all_button=self.button('全選',lambda:self.set_all(True));selectbar.addWidget(self.select_all_button)
        self.select_none_button=self.button('全不選',lambda:self.set_all(False));selectbar.addWidget(self.select_none_button)
        left.addLayout(selectbar)
        self.table=SourceTable();self.table.setHorizontalHeaderLabels(['收錄','摘要內容',''])
        self.table.verticalHeader().hide();self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed);self.table.setColumnWidth(0,48)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed);self.table.setColumnWidth(2,54)
        self.table.horizontalHeader().sectionResized.connect(lambda *_:QTimer.singleShot(0,self.table.resizeRowsToContents))
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.setWordWrap(True);left.addWidget(self.table,1)
        self.table.remove_requested.connect(self.remove_items)
        self.table.itemChanged.connect(self.check_changed)
        self.table.itemSelectionChanged.connect(self.refresh)
        self.table.itemDoubleClicked.connect(lambda *_:self.add_selected())
        self.count_label=QLabel();self.count_label.setObjectName('muted');left.addWidget(self.count_label)
        self.api_button=self.button('OpenAI 金鑰設定（選用）',self.open_api_dialog);left.addWidget(self.api_button)
        self.undo_button=self.button('復原上次整理',self.undo_rewrite);left.addWidget(self.undo_button)
        self.splitter.addWidget(list_panel)
        transfer=QWidget();transfer.setFixedWidth(102);arrows=QVBoxLayout(transfer);arrows.setContentsMargins(2,0,2,0)
        arrows.addStretch()
        self.target_label=QLabel();self.target_label.setWordWrap(True);self.target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.target_label.setObjectName('muted');arrows.addWidget(self.target_label)
        self.add_selected_button=self.button('加入 →',self.add_selected,True);arrows.addWidget(self.add_selected_button)
        self.add_all_button=self.button('全部加入',self.add_all);arrows.addWidget(self.add_all_button)
        arrows.addStretch()
        right_panel=QWidget();right=QVBoxLayout(right_panel);right.setContentsMargins(0,0,0,0);right.setSpacing(6)
        row=QHBoxLayout();row.addWidget(QLabel('會議紀錄'));tip=QLabel('拖到標題或段落加入 · 文字可直接編輯');tip.setObjectName('muted');row.addWidget(tip);row.addStretch()
        row.addWidget(self.button('新增空白',self.add_item));row.addWidget(self.button('全部移除',self.remove_all));right.addLayout(row)
        self.preview=DocumentEditor();self.preview.edited.connect(self.document_changed)
        self.preview.insert_requested.connect(self.insert_items);self.preview.remove_requested.connect(self.remove_items)
        self.preview.target_changed.connect(self.choose_target);right.addWidget(self.preview,1)
        destination=QWidget();destination_layout=QHBoxLayout(destination);destination_layout.setContentsMargins(0,0,0,0);destination_layout.setSpacing(4)
        destination_layout.addWidget(transfer);destination_layout.addWidget(right_panel,1)
        self.splitter.addWidget(destination);self.splitter.setSizes([430,900]);self.splitter.setStretchFactor(1,1)
        review_layout.addWidget(self.splitter);self.pages.addWidget(review_page)
        bottom=QHBoxLayout();self.status=QLabel('貼上摘要後按「下一步」。');self.status.setObjectName('muted')
        self.status.setWordWrap(True);bottom.addWidget(self.status,1)
        self.export_button=self.button('匯出 Word',self.export_word,True);bottom.addWidget(self.export_button);layout.addLayout(bottom)
        self.create_api_dialog();self.pages.currentChanged.connect(self.page_changed)
        self.set_project(self.project)

    def button(self,text,callback,primary=False):
        button=QPushButton(text);button.clicked.connect(callback)
        if primary:button.setObjectName('primary')
        return button

    def create_api_dialog(self):
        self.api_dialog=QDialog(self);self.api_dialog.setWindowTitle('選用 OpenAI 整理');self.api_dialog.resize(560,230)
        layout=QVBoxLayout(self.api_dialog)
        note=QLabel('只有按下「整理右側文字」才會將會議紀錄內容傳送至 OpenAI。\n費用由你的帳戶支付；金鑰只保留在本次開啟期間。')
        note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout();self.key_input=QLineEdit();self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText('輸入自己的金鑰');form.addRow('金鑰',self.key_input)
        self.model_input=QLineEdit(DEFAULT_MODEL);form.addRow('模型',self.model_input);layout.addLayout(form)
        row=QHBoxLayout();row.addWidget(self.button('關閉',self.api_dialog.reject));row.addStretch()
        self.rewrite_button=self.button('整理右側文字',self.start_rewrite,True);row.addWidget(self.rewrite_button);layout.addLayout(row)

    def open_api_dialog(self):
        self.refresh();self.api_dialog.exec()

    def page_changed(self,index):
        self.step1_button.setChecked(index==0);self.step2_button.setChecked(index==1)
        self.export_button.setVisible(index==1)

    def changed(self):
        if not self._loading:self.dirty=True;self.refresh()

    def pending_source(self):return self.project.source!=self.project.parsed_source

    def source_changed(self):
        if self._loading:return
        self.project.source=self.source_input.toPlainText();self.changed()
        if self.pending_source():self.status.setText('文字已變更，按「下一步」重新轉換。')

    def confirm(self,title,text,yes='繼續',no='取消'):
        box=QMessageBox(self);box.setWindowTitle(title);box.setText(text)
        accept=box.addButton(yes,QMessageBox.ButtonRole.AcceptRole)
        box.addButton(no,QMessageBox.ButtonRole.RejectRole);box.exec()
        return box.clickedButton()==accept

    def go_review(self):
        if self.pending_source() or not self.project.items:self.split_source()
        else:self.pages.setCurrentIndex(1)
        self.page_changed(self.pages.currentIndex())

    def split_source(self):
        if not self.source_input.toPlainText().strip():self.status.setText('請先貼上文字摘要。');return
        if self.project.items and not self.confirm('重新轉換','重新轉換會取代條目及其編輯內容；已填的標題與基本資料會保留。','重新轉換'):return
        self.project.source=self.source_input.toPlainText();self.project.parsed_source=self.project.source
        self.project.items=parse_summary(self.project.source);self.project.used_openai=False
        self.project.source_order=[]
        self.reset_transfer()
        self.before_rewrite=None;self.rewritten_texts={};self.populate();self.changed();self.pages.setCurrentIndex(1)
        self.status.setText('已收錄全部內容。取消勾選可移除，重新勾選可恢復；也可拖曳調整右側位置。')

    def set_project(self,project):
        self.project=project;self.before_rewrite=None;self.rewritten_texts={};self._loading=True
        self.reset_transfer()
        self.source_input.setPlainText(project.source);self._loading=False
        self.populate();self.dirty=False;self.refresh()
        self.pages.setCurrentIndex(1 if project.items and not self.pending_source() else 0)
        self.page_changed(self.pages.currentIndex())

    def populate(self):
        self._loading=True;selected=set(self.table.selected_ids());self.table.setRowCount(0)
        self.table.setColumnHidden(2,not any(not i.source.strip() for i in self.project.items))
        source_positions={key:index for index,key in enumerate(self.source_order)}
        ordered=sorted(self.project.items,key=lambda i:source_positions.get(i.id,len(source_positions)))
        for index,item in enumerate(ordered):
            self.table.insertRow(index)
            flags=Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|Qt.ItemFlag.ItemIsDragEnabled
            state=QTableWidgetItem();state.setFlags(flags|Qt.ItemFlag.ItemIsUserCheckable)
            state.setData(Qt.ItemDataRole.UserRole,item.id)
            state.setCheckState(Qt.CheckState.Checked if item.included else Qt.CheckState.Unchecked)
            state.setToolTip('勾選收錄；取消勾選保留修訂，之後可加回原位。');self.table.setItem(index,0,state)
            content=traditional(item.source).replace('**','').replace('__','') or item.text or '（手動新增的空白段落）'
            cell=QTableWidgetItem(content);cell.setFlags(flags)
            cell.setData(Qt.ItemDataRole.UserRole,item.id);cell.setToolTip((item.topic+'\n' if item.topic else '')+'拖曳整段到右側；原始文字會保留。');self.table.setItem(index,1,cell)
            if not item.source.strip():
                delete=self.button('刪除',lambda checked=False,key=item.id:self.delete_manual_item(key))
                delete.setToolTip('刪除這筆手動新增段落，從左右兩側及專案中移除')
                delete.setAccessibleName('刪除手動新增段落')
                delete.setStyleSheet('QPushButton { padding:2px; min-width:0; border:none; color:#9b423e; background:transparent; } QPushButton:hover { background:#fceeed; }')
                self.table.setCellWidget(index,2,delete)
            if item.id in selected:
                state.setSelected(True);cell.setSelected(True)
        self.table.resizeRowsToContents();self._loading=False
        self.preview.set_project(self.project)
        self.refresh()

    def current_item(self):
        row=self.table.currentRow()
        key=self.table.item(row,1).data(Qt.ItemDataRole.UserRole) if row>=0 else None
        return next((i for i in self.project.items if i.id==key),None)

    def check_changed(self,cell):
        if self._loading or cell.column()!=0 or self.job is not None:return
        key=cell.data(Qt.ItemDataRole.UserRole)
        item=next((item for item in self.project.items if item.id==key),None)
        if item is None:return
        item.included=cell.checkState()==Qt.CheckState.Checked
        self.preview.set_project(self.project);self.changed()
        self.status.setText('已重新收錄，保留原有位置與修訂。' if item.included else '已取消收錄，修訂仍保留，勾回即可恢復。')

    def reset_transfer(self):
        self.session_token=uuid4().hex;self.table.token=self.session_token;self.preview.token=self.session_token
        known={i.id for i in self.project.items}
        self.source_order=list(dict.fromkeys([key for key in self.project.source_order if key in known]+[i.id for i in self.project.items]))
        self.project.source_order=self.source_order
        self.target_section='chair';self.preview.active_section='chair'

    def choose_target(self,section):
        if section in SECTIONS:self.target_section=section;self.refresh()

    def insert_items(self,ids,section,before=''):
        if section not in SECTIONS or self.job is not None:return
        known={item.id:item for item in self.project.items}
        ids=list(dict.fromkeys(key for key in ids if key in known))
        if not ids or before in ids:return
        moving=[known[key] for key in ids]
        remainder=[i for i in self.project.items if i.id not in ids]
        index=next((n for n,i in enumerate(remainder) if i.id==before and i.section==section),len(remainder))
        for item in moving:item.included=True;item.section=section
        self.project.items=remainder[:index]+moving+remainder[index:]
        self.target_section=section;self.preview.active_section=section
        self.populate();self.changed()
        QTimer.singleShot(0,lambda:self.preview.reveal(moving[0].id))
        self.status.setText(f'已加入 {len(moving)} 段，可在右側直接編輯；拖曳段落左側把手可調整位置。')

    def add_selected(self):
        pending={i.id for i in self.project.items if not i.included}
        self.insert_items([key for key in self.table.selected_ids() if key in pending],self.target_section)

    def add_all(self):
        pending={item.id for item in self.project.items if not item.included}
        self.insert_items([key for key in self.source_order if key in pending],self.target_section)

    def remove_items(self,ids):
        if self.job is not None:return
        for item in self.project.items:
            if item.id in ids:item.included=False
        self.populate();self.changed();self.status.setText('已移除；左側原文與右側修訂仍保留，可隨時重新加入。')

    def remove_all(self):self.remove_items([i.id for i in self.project.items if i.included])

    def delete_manual_item(self,key):
        if self.job is not None:return
        item=next((i for i in self.project.items if i.id==key),None)
        # Parsed source paragraphs always retain their original text. Empty
        # source identifies manual additions, including existing saved projects.
        if item is None or item.source.strip():return
        if item.text.strip() and not self.confirm('刪除手動段落',
                '這筆手動新增段落已有文字。刪除後會從左右兩側與專案中移除，確定刪除？','刪除'):return
        self.project.items=[i for i in self.project.items if i.id!=key]
        self.source_order[:]=[item_id for item_id in self.source_order if item_id!=key]
        self.rewritten_texts.pop(key,None)
        self.populate();self.changed();self.status.setText('已刪除手動新增段落。')

    def document_changed(self,kind,key,text):
        if self._loading:return
        value=traditional(text)
        if kind=='item':
            for index,item in enumerate(self.project.items):
                if item.id==key:
                    item.text=value;break
        else:self.project.document_edits[key]=value
        self.preview.sync_prefixes(self.project)
        self.changed()

    def set_all(self,included):
        if self.job is not None:return
        for item in self.project.items:item.included=included
        self.populate();self.changed()
        self.status.setText('已收錄全部內容，保留各段位置與修訂。' if included else '已取消全部收錄，勾選或拖曳即可重新加入。')

    def add_item(self):
        section=self.target_section
        self.project.items.append(SummaryItem(source='',text='',section=section))
        self.source_order.append(self.project.items[-1].id)
        self.populate();self.table.setCurrentCell(len(self.project.items)-1,1)
        edit=self.preview.edits[self.project.items[-1].id];edit.setFocus()
        item_id=self.project.items[-1].id
        def reveal_added():
            # Row heights and scroll ranges settle after the list is rebuilt.
            # Resolve by ID in case another action changed the rows meanwhile.
            self.table.doItemsLayout()
            for row in range(self.table.rowCount()):
                cell=self.table.item(row,0)
                if cell.data(Qt.ItemDataRole.UserRole)==item_id:
                    self.table.scrollToItem(cell,QTableWidget.ScrollHint.PositionAtBottom)
                    self.preview.reveal(item_id);break
        QTimer.singleShot(0,reveal_added);self.changed()

    def refresh(self):
        if self._loading:return
        selected=len(self.project.selected());self.count_label.setText(f'已加入 {sum(i.included for i in self.project.items)} / {len(self.project.items)} 段 · 可按 Ctrl 多選')
        self.target_label.setText('加入至\n'+SECTIONS[self.target_section])
        pending={i.id for i in self.project.items if not i.included}
        self.add_selected_button.setEnabled(bool(pending.intersection(self.table.selected_ids())) and self.job is None)
        self.add_all_button.setEnabled(any(not i.included for i in self.project.items) and self.job is None)
        allowed=bool(selected) and not self.pending_source() and self.job is None
        self.export_button.setEnabled(allowed);self.rewrite_button.setEnabled(allowed)
        self.undo_button.setVisible(self.before_rewrite is not None)
        self.undo_button.setEnabled(self.before_rewrite is not None and self.job is None)
        self.setWindowTitle(('＊ ' if self.dirty else '')+'會議摘要整理 '+__version__)

    def start_rewrite(self):
        if not self.key_input.text().strip():
            self.key_input.setFocus();self.key_input.setPlaceholderText('請先輸入 OpenAI 金鑰');return
        if not self.project.selected() or self.pending_source() or self.job is not None:return
        self.api_dialog.accept();self.job=RewriteJob(self.project,self.key_input.text(),self.model_input.text(),self)
        self.job.completed.connect(self.apply_rewrite);self.job.failed.connect(self.status.setText)
        self.job.progress.connect(self.status.setText);self.job.finished.connect(self.job_finished)
        self.set_busy(True);self.job.start()

    def set_busy(self,busy):
        for control in (self.pages,self.step1_button,self.step2_button,self.new_button,self.open_button,self.save_button):control.setEnabled(not busy)
        self.refresh()

    def job_finished(self):
        job=self.job;self.job=None
        if job:job.deleteLater()
        self.set_busy(False)

    def apply_rewrite(self,updates):
        self.before_rewrite=self.project.model_copy(deep=True);self.rewritten_texts=dict(updates)
        for item in self.project.items:
            if item.id in updates:item.text=updates[item.id]
        self.project.used_openai=True;self.populate();self.changed();self.status.setText('已整理完成，可直接修改，或復原上次整理。')

    def undo_rewrite(self):
        if self.before_rewrite:
            previous=self.before_rewrite;texts={i.id:i.text for i in previous.items};kept_manual=False
            for item in self.project.items:
                if item.id in self.rewritten_texts:
                    if item.text==self.rewritten_texts[item.id]:item.text=texts[item.id]
                    else:kept_manual=True
            self.project.used_openai=previous.used_openai or kept_manual;self.before_rewrite=None;self.rewritten_texts={}
            self.populate();self.changed();self.status.setText('已復原；之後手動修改的文字已保留。')

    def can_discard(self):
        if not self.dirty:return True
        box=QMessageBox(self);box.setWindowTitle('尚未儲存');box.setText('目前專案有未儲存的變更。')
        save=box.addButton('儲存專案',QMessageBox.ButtonRole.AcceptRole)
        discard=box.addButton('捨棄變更',QMessageBox.ButtonRole.DestructiveRole)
        box.addButton('取消',QMessageBox.ButtonRole.RejectRole);box.exec()
        if box.clickedButton()==save:return self.save_project()
        return box.clickedButton()==discard

    def new_project(self):
        if self.can_discard():self.path=None;self.set_project(SummaryProject());self.status.setText('貼上新會議摘要後按「下一步」。')

    def open_project(self):
        if not self.can_discard():return
        path,_=QFileDialog.getOpenFileName(self,'開啟摘要專案','','摘要專案 (*.summary.json)')
        if not path:return
        try:project=load_summary(path)
        except (ValueError,OSError):self.status.setText('無法開啟，請選擇本程式儲存的摘要專案。');return
        self.path=Path(path);self.set_project(project)
        self.status.setText('已載入專案。'+('請按下一步重新轉換已變更的來源文字。' if self.pending_source() else '可直接編輯。'))

    def save_project(self):
        path,_=QFileDialog.getSaveFileName(self,'儲存摘要專案',str(self.path or '會議摘要.summary.json'),'摘要專案 (*.summary.json)')
        if not path:return False
        if not path.lower().endswith('.summary.json'):path+='.summary.json'
        try:save_summary(self.project,path)
        except OSError:self.status.setText('無法儲存，請確認資料夾權限或選擇其他位置。');return False
        self.path=Path(path);self.dirty=False;self.refresh();self.status.setText('專案已儲存，不包含金鑰。');return True

    def export_word(self):
        path,_=QFileDialog.getSaveFileName(self,'匯出會議紀錄','處務會議紀錄.docx','Word 文件 (*.docx)')
        if not path:return
        if not path.lower().endswith('.docx'):path+='.docx'
        try:export_summary(self.project,path)
        except (OSError,ValueError):self.status.setText('匯出失敗，請確認右側內容、關閉同名 Word 文件，或改存其他位置。');return
        self.status.setText('已匯出：'+path)

    def closeEvent(self,event):
        if self.job is not None:self.status.setText('文字整理進行中，請等待完成再關閉。');event.ignore();return
        if self.can_discard():self.key_input.clear();event.accept()
        else:event.ignore()
