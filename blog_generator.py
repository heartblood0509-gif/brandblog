import sys
import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTextEdit, QPushButton, QLabel,
                             QLineEdit, QFileDialog, QComboBox, QStatusBar,
                             QSplitter, QGroupBox, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor
from google import genai
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime

# 환경 변수 로드
load_dotenv()


class CrawlThread(QThread):
    """URL에서 블로그 글을 크롤링하는 스레드 (Playwright 사용)"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            # Playwright를 사용한 크롤링
            with sync_playwright() as p:
                # 헤드리스 모드로 브라우저 실행
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = context.new_page()

                # 페이지 로드 (네트워크 대기)
                page.goto(self.url, wait_until='networkidle', timeout=30000)

                # 네이버 블로그 감지
                if 'blog.naver.com' in self.url:
                    content = self.extract_naver_blog_playwright(page)
                # 티스토리 블로그 감지
                elif 'tistory.com' in self.url:
                    content = self.extract_tistory_blog_playwright(page)
                # 일반 블로그/웹사이트
                else:
                    content = self.extract_general_content_playwright(page)

                browser.close()

                if content:
                    self.finished.emit(content)
                else:
                    self.error.emit("블로그 내용을 추출할 수 없습니다. 직접 복사해서 붙여넣어 주세요.")

        except Exception as e:
            self.error.emit(f"크롤링 오류: {str(e)}")

    def extract_naver_blog_playwright(self, page):
        """네이버 블로그 콘텐츠 추출 (Playwright)"""
        try:
            # iframe이 있는지 확인
            frames = page.frames
            main_frame = None

            # mainFrame 찾기
            for frame in frames:
                if 'mainFrame' in frame.url or frame.name == 'mainFrame':
                    main_frame = frame
                    break

            if main_frame:
                # iframe 내부 콘텐츠 대기
                main_frame.wait_for_selector('.se-main-container, #postViewArea', timeout=10000)

                # 제목 추출
                title = ""
                try:
                    title_elem = main_frame.query_selector('.se-title-text, .pcol1')
                    if title_elem:
                        title = title_elem.inner_text()
                except:
                    pass

                # 본문 추출
                content_elem = main_frame.query_selector('.se-main-container, #postViewArea')
                if content_elem:
                    content = content_elem.inner_text()
                    if title:
                        return f"{title}\n\n{content}"
                    return content
            else:
                # iframe이 없는 경우 직접 추출
                page.wait_for_selector('.se-main-container, #postViewArea', timeout=10000)

                title = ""
                try:
                    title_elem = page.query_selector('.se-title-text, .pcol1')
                    if title_elem:
                        title = title_elem.inner_text()
                except:
                    pass

                content_elem = page.query_selector('.se-main-container, #postViewArea')
                if content_elem:
                    content = content_elem.inner_text()
                    if title:
                        return f"{title}\n\n{content}"
                    return content
        except Exception as e:
            print(f"네이버 블로그 추출 오류: {e}")
        return None

    def extract_tistory_blog_playwright(self, page):
        """티스토리 블로그 콘텐츠 추출 (Playwright)"""
        try:
            # 본문 로딩 대기
            page.wait_for_selector('article, .entry-content, .contents_style', timeout=10000)

            # 제목 추출
            title = ""
            try:
                title_elem = page.query_selector('h1.tit_post, h2.title, .title_post')
                if title_elem:
                    title = title_elem.inner_text()
            except:
                pass

            # 본문 추출
            content_elem = page.query_selector('.contents_style, .entry-content, article')
            if content_elem:
                content = content_elem.inner_text()
                if title:
                    return f"{title}\n\n{content}"
                return content
        except Exception as e:
            print(f"티스토리 블로그 추출 오류: {e}")
        return None

    def extract_general_content_playwright(self, page):
        """일반 웹사이트 콘텐츠 추출 (Playwright)"""
        try:
            # 일반적인 콘텐츠 영역 대기
            page.wait_for_selector('article, main, .post-content, .entry-content', timeout=10000)

            # 여러 선택자 시도
            selectors = [
                'article',
                'main',
                '.post-content',
                '.entry-content',
                '.content',
                '[role="main"]'
            ]

            for selector in selectors:
                try:
                    content_elem = page.query_selector(selector)
                    if content_elem:
                        text = content_elem.inner_text()
                        if text and len(text) > 100:  # 최소 100자 이상
                            return text
                except:
                    continue

            # 모든 p 태그 텍스트 가져오기 (최후의 수단)
            p_elements = page.query_selector_all('p')
            if p_elements:
                paragraphs = [p.inner_text() for p in p_elements if p.inner_text().strip()]
                if paragraphs:
                    return '\n\n'.join(paragraphs)

        except Exception as e:
            print(f"일반 콘텐츠 추출 오류: {e}")
        return None

    def extract_naver_blog(self, soup):
        """네이버 블로그 콘텐츠 추출"""
        # 네이버 블로그는 iframe 내부에 콘텐츠가 있음
        # mainFrame이라는 iframe의 src를 가져와서 다시 크롤링해야 함
        try:
            # 제목 추출
            title = soup.find('h3', class_='se_textarea')
            if not title:
                title = soup.find('div', class_='se-title-text')

            # 본문 추출
            content_area = soup.find('div', class_='se-main-container')
            if not content_area:
                content_area = soup.find('div', id='postViewArea')

            if content_area:
                # 텍스트만 추출
                text = content_area.get_text(separator='\n', strip=True)
                if title:
                    return f"{title.get_text(strip=True)}\n\n{text}"
                return text
        except:
            pass
        return None

    def extract_tistory_blog(self, soup):
        """티스토리 블로그 콘텐츠 추출"""
        try:
            # 제목 추출
            title = soup.find('h1', class_='tit_post') or soup.find('h2', class_='title')

            # 본문 추출
            content_area = soup.find('div', class_='contents_style') or \
                          soup.find('div', class_='entry-content') or \
                          soup.find('article')

            if content_area:
                text = content_area.get_text(separator='\n', strip=True)
                if title:
                    return f"{title.get_text(strip=True)}\n\n{text}"
                return text
        except:
            pass
        return None

    def extract_general_content(self, soup):
        """일반 웹사이트 콘텐츠 추출"""
        try:
            # 일반적인 블로그 구조에서 콘텐츠 추출
            # article, main, .post, .entry 등의 일반적인 클래스/태그 시도
            content_area = soup.find('article') or \
                          soup.find('main') or \
                          soup.find('div', class_='post-content') or \
                          soup.find('div', class_='entry-content') or \
                          soup.find('div', class_='content')

            if content_area:
                # script, style 태그 제거
                for script in content_area(['script', 'style', 'nav', 'header', 'footer']):
                    script.decompose()

                text = content_area.get_text(separator='\n', strip=True)
                return text

            # 모든 p 태그의 텍스트 가져오기 (최후의 수단)
            paragraphs = soup.find_all('p')
            if paragraphs:
                return '\n\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])

        except:
            pass
        return None


class AnalyzeThread(QThread):
    """레퍼런스 글 분석을 백그라운드에서 처리하는 스레드"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, client, reference_text):
        super().__init__()
        self.client = client
        self.reference_text = reference_text

    def run(self):
        try:
            prompt = f"""다음 블로그 글을 분석하여 구조와 특징을 추출해주세요.

레퍼런스 글:
{self.reference_text}

다음 항목들을 분석해주세요:
1. 제목 패턴 및 스타일
2. 서론 구성 방식 (문제 제기, 공감, 호기심 유발 등)
3. 본론 섹션 개수와 각 섹션의 구조
4. 소제목 스타일과 패턴
5. 문단 길이와 구성 방식
6. 결론 방식 (요약, CTA, 질문 등)
7. 특징적인 문체 요소 (문장 길이, 어조, 키워드 사용 등)
8. 전체적인 글의 톤 앤 매너

각 항목에 대해 구체적으로 분석하고, 이 스타일을 재현하기 위한 핵심 요소를 정리해주세요."""

            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            analysis_result = response.text
            self.finished.emit(analysis_result)

        except Exception as e:
            self.error.emit(str(e))


class GenerateThread(QThread):
    """새 글 생성을 백그라운드에서 처리하는 스레드"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, client, reference_text, analysis_result, topic, keywords, requirements):
        super().__init__()
        self.client = client
        self.reference_text = reference_text
        self.analysis_result = analysis_result
        self.topic = topic
        self.keywords = keywords
        self.requirements = requirements

    def run(self):
        try:
            prompt = f"""당신은 브랜드 블로그 콘텐츠 작성 전문가입니다.

# 레퍼런스 글 분석 결과
{self.analysis_result}

# 새로운 글 작성 요청
- 주제: {self.topic}
- 타겟 키워드: {self.keywords}
- 추가 요구사항: {self.requirements if self.requirements else '없음'}

위의 분석 결과를 바탕으로, 새로운 주제에 대해 **구조와 스타일만 참고하여** 완전히 새로운 블로그 글을 작성해주세요.

⚠️ 절대 금지 사항:
- 레퍼런스 글의 문장을 그대로 복사하거나 살짝 바꾸는 것
- 레퍼런스의 특정 표현이나 단어를 그대로 가져오는 것
- 레퍼런스와 유사한 예시나 사례를 사용하는 것

✅ 반드시 지켜야 할 사항:
1. **글 구조**: 레퍼런스의 전체 구조(서론-본론-결론 구성, 섹션 개수)만 참고
2. **제목/소제목 스타일**: 형식(질문형, 숫자형 등)만 참고하되, 완전히 새로운 문장으로 작성
3. **문체와 톤**: 어조(친근함, 전문성 등), 문장 길이 스타일만 모방
4. **내용**: 주제에 맞는 완전히 새로운 내용, 예시, 근거 작성
5. **키워드**: {self.keywords}를 자연스럽게 포함
6. **독창성**: 레퍼런스를 읽지 않은 사람이 쓴 것처럼 완전히 새로운 글

작성 방식:
- 레퍼런스의 "어떻게 쓰여졌는가"(구조, 스타일)만 학습
- "무엇이 쓰여졌는가"(구체적 내용, 문장)는 완전히 무시
- {self.topic}에 대한 독창적인 내용으로 채우기

완성된 블로그 글만 출력해주세요 (분석이나 설명 없이)."""

            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            generated_content = response.text
            self.finished.emit(generated_content)

        except Exception as e:
            self.error.emit(str(e))


class BlogGeneratorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.client = None
        self.supabase = None
        self.current_project_id = None
        self.analysis_result = ""
        self.init_gemini_client()
        self.init_supabase_client()
        self.init_ui()

    def init_gemini_client(self):
        """Gemini API 클라이언트 초기화"""
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            QMessageBox.warning(self, "API Key 없음",
                              ".env 파일에 GEMINI_API_KEY를 설정해주세요.")

    def init_supabase_client(self):
        """Supabase 클라이언트 초기화"""
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if url and key:
            self.supabase: Client = create_client(url, key)

    def init_ui(self):
        """UI 초기화"""
        self.setWindowTitle("브랜드 블로그 자동 생성 도구")
        self.setGeometry(100, 100, 1400, 900)

        # 다크 모드 스타일 적용
        self.apply_dark_theme()

        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 메인 레이아웃
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # 상단 헤더 (타이틀 + 초기화 버튼)
        header_layout = QHBoxLayout()

        title_label = QLabel("🚀 브랜드 블로그 자동 생성 도구")
        title_label.setFont(QFont("Arial", 20, QFont.Bold))
        title_label.setStyleSheet("color: #00d4ff; padding: 10px;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        reset_btn = QPushButton("🔄 전체 초기화")
        reset_btn.setStyleSheet(self.get_button_style("#ff4444"))
        reset_btn.setMinimumHeight(40)
        reset_btn.setMinimumWidth(150)
        reset_btn.clicked.connect(self.reset_all)
        header_layout.addWidget(reset_btn)

        main_layout.addLayout(header_layout)

        # 수평 스플리터 (왼쪽/오른쪽 패널)
        splitter = QSplitter(Qt.Horizontal)

        # 왼쪽 패널 (레퍼런스)
        left_panel = self.create_reference_panel()
        splitter.addWidget(left_panel)

        # 오른쪽 패널 (생성)
        right_panel = self.create_generation_panel()
        splitter.addWidget(right_panel)

        splitter.setSizes([700, 700])
        main_layout.addWidget(splitter)

        # 상태 표시줄
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("준비 완료")
        self.status_bar.setStyleSheet("background-color: #1e1e1e; color: #aaaaaa; padding: 5px;")

    def create_reference_panel(self):
        """레퍼런스 패널 생성"""
        panel = QGroupBox("📝 레퍼런스 글")
        panel.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00d4ff;
                border: 2px solid #333333;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        # URL 입력 섹션
        url_label = QLabel("블로그 URL:")
        url_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        layout.addWidget(url_label)

        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("블로그 글 URL을 입력하세요 (예: https://blog.naver.com/...)")
        self.url_input.setStyleSheet(self.get_line_edit_style())
        self.url_input.setMinimumHeight(35)
        url_layout.addWidget(self.url_input)

        crawl_btn = QPushButton("🌐 URL 크롤링")
        crawl_btn.setStyleSheet(self.get_button_style("#9d4eff"))
        crawl_btn.setMinimumHeight(35)
        crawl_btn.setMinimumWidth(120)
        crawl_btn.clicked.connect(self.crawl_url)
        url_layout.addWidget(crawl_btn)

        layout.addLayout(url_layout)

        # 또는 라벨
        or_label = QLabel("또는")
        or_label.setStyleSheet("color: #666666; text-align: center; padding: 5px;")
        or_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(or_label)

        # 파일 불러오기 버튼
        load_btn = QPushButton("📂 파일 불러오기")
        load_btn.setStyleSheet(self.get_button_style("#4a9eff"))
        load_btn.setMinimumHeight(40)
        load_btn.clicked.connect(self.load_reference_file)
        layout.addWidget(load_btn)

        # 레퍼런스 텍스트 박스
        self.reference_text = QTextEdit()
        self.reference_text.setPlaceholderText("레퍼런스 글을 입력하거나 파일을 불러오세요...")
        self.reference_text.setStyleSheet(self.get_text_edit_style())
        layout.addWidget(self.reference_text)

        # 구조 분석 버튼
        analyze_btn = QPushButton("🔍 구조 분석")
        analyze_btn.setStyleSheet(self.get_button_style("#00d4ff"))
        analyze_btn.setMinimumHeight(40)
        analyze_btn.clicked.connect(self.analyze_reference)
        layout.addWidget(analyze_btn)

        # 분석 결과 표시
        analysis_label = QLabel("분석 결과:")
        analysis_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        layout.addWidget(analysis_label)

        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setPlaceholderText("분석 결과가 여기에 표시됩니다...")
        self.analysis_text.setStyleSheet(self.get_text_edit_style())
        self.analysis_text.setMaximumHeight(200)
        layout.addWidget(self.analysis_text)

        panel.setLayout(layout)
        return panel

    def create_generation_panel(self):
        """새 글 생성 패널 생성"""
        panel = QGroupBox("✨ 새 글 생성")
        panel.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ff88;
                border: 2px solid #333333;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 주제 입력
        topic_label = QLabel("주제:")
        topic_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        layout.addWidget(topic_label)

        self.topic_input = QLineEdit()
        self.topic_input.setPlaceholderText("예: 겨울철 피부 관리 방법")
        self.topic_input.setStyleSheet(self.get_line_edit_style())
        self.topic_input.setMinimumHeight(35)
        layout.addWidget(self.topic_input)

        # 타겟 키워드 입력
        keywords_label = QLabel("타겟 키워드 (쉼표로 구분):")
        keywords_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        layout.addWidget(keywords_label)

        self.keywords_input = QLineEdit()
        self.keywords_input.setPlaceholderText("예: 보습, 수분크림, 건조함")
        self.keywords_input.setStyleSheet(self.get_line_edit_style())
        self.keywords_input.setMinimumHeight(35)
        layout.addWidget(self.keywords_input)

        # 추가 요구사항
        requirements_label = QLabel("추가 요구사항 (선택):")
        requirements_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        layout.addWidget(requirements_label)

        self.requirements_input = QTextEdit()
        self.requirements_input.setPlaceholderText("예: 20대 여성 타겟, 친근한 어조 사용...")
        self.requirements_input.setStyleSheet(self.get_text_edit_style())
        self.requirements_input.setMaximumHeight(80)
        layout.addWidget(self.requirements_input)

        # 글 생성 버튼
        generate_btn = QPushButton("🎨 글 생성")
        generate_btn.setStyleSheet(self.get_button_style("#00ff88"))
        generate_btn.setMinimumHeight(45)
        generate_btn.clicked.connect(self.generate_content)
        layout.addWidget(generate_btn)

        # 생성된 글 텍스트 박스
        generated_label = QLabel("생성된 글:")
        generated_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        layout.addWidget(generated_label)

        self.generated_text = QTextEdit()
        self.generated_text.setPlaceholderText("생성된 글이 여기에 표시됩니다...")
        self.generated_text.setStyleSheet(self.get_text_edit_style())
        layout.addWidget(self.generated_text)

        # 저장 옵션
        save_layout = QHBoxLayout()

        self.format_combo = QComboBox()
        self.format_combo.addItems([".txt", ".md", ".html (네이버 블로그용)"])
        self.format_combo.setStyleSheet(self.get_combo_style())
        self.format_combo.setMinimumHeight(35)
        save_layout.addWidget(self.format_combo)

        save_btn = QPushButton("💾 저장")
        save_btn.setStyleSheet(self.get_button_style("#ff6b9d"))
        save_btn.setMinimumHeight(35)
        save_btn.clicked.connect(self.save_content)
        save_layout.addWidget(save_btn)

        layout.addLayout(save_layout)

        panel.setLayout(layout)
        return panel

    def apply_dark_theme(self):
        """다크 모드 테마 적용"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0d1117;
            }
            QWidget {
                background-color: #0d1117;
                color: #c9d1d9;
            }
            QTextEdit, QLineEdit {
                background-color: #161b22;
                color: #c9d1d9;
                border: 2px solid #30363d;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
            }
            QTextEdit:focus, QLineEdit:focus {
                border: 2px solid #58a6ff;
            }
        """)

    def get_button_style(self, color):
        """버튼 스타일 반환"""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.adjust_color_brightness(color, 1.2)};
            }}
            QPushButton:pressed {{
                background-color: {self.adjust_color_brightness(color, 0.8)};
            }}
            QPushButton:disabled {{
                background-color: #30363d;
                color: #6e7681;
            }}
        """

    def get_text_edit_style(self):
        """텍스트 에디트 스타일 반환"""
        return """
            QTextEdit {
                background-color: #161b22;
                color: #c9d1d9;
                border: 2px solid #30363d;
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
                line-height: 1.6;
            }
            QTextEdit:focus {
                border: 2px solid #58a6ff;
            }
        """

    def get_line_edit_style(self):
        """라인 에디트 스타일 반환"""
        return """
            QLineEdit {
                background-color: #161b22;
                color: #c9d1d9;
                border: 2px solid #30363d;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #58a6ff;
            }
        """

    def get_combo_style(self):
        """콤보박스 스타일 반환"""
        return """
            QComboBox {
                background-color: #161b22;
                color: #c9d1d9;
                border: 2px solid #30363d;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QComboBox:focus {
                border: 2px solid #58a6ff;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #161b22;
                color: #c9d1d9;
                selection-background-color: #58a6ff;
            }
        """

    def adjust_color_brightness(self, hex_color, factor):
        """색상 밝기 조정"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        rgb = tuple(min(255, int(c * factor)) for c in rgb)
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def crawl_url(self):
        """URL에서 블로그 글 크롤링"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "입력 오류", "블로그 URL을 입력해주세요.")
            return

        if not url.startswith('http'):
            QMessageBox.warning(self, "입력 오류", "올바른 URL 형식이 아닙니다.\n(http:// 또는 https://로 시작해야 합니다)")
            return

        self.status_bar.showMessage("URL 크롤링 중...")
        self.reference_text.setPlainText("크롤링 중입니다. 잠시만 기다려주세요...")

        # 크롤링 스레드 시작
        self.crawl_thread = CrawlThread(url)
        self.crawl_thread.finished.connect(self.on_crawl_finished)
        self.crawl_thread.error.connect(self.on_crawl_error)
        self.crawl_thread.start()

    def on_crawl_finished(self, content):
        """크롤링 완료 처리"""
        self.reference_text.setPlainText(content)
        self.status_bar.showMessage("크롤링 완료!")
        QMessageBox.information(self, "완료", "블로그 글을 성공적으로 가져왔습니다!")

    def on_crawl_error(self, error):
        """크롤링 오류 처리"""
        self.reference_text.setPlainText("")
        self.status_bar.showMessage("크롤링 실패")
        QMessageBox.critical(self, "오류", f"크롤링 중 오류가 발생했습니다:\n{error}\n\n직접 복사해서 붙여넣어 주세요.")

    def load_reference_file(self):
        """레퍼런스 파일 불러오기"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "레퍼런스 파일 선택",
            "",
            "Text Files (*.txt *.md);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.reference_text.setPlainText(content)
                    self.status_bar.showMessage(f"파일 로드 완료: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"파일을 불러올 수 없습니다:\n{str(e)}")

    def analyze_reference(self):
        """레퍼런스 글 분석"""
        if not self.client:
            QMessageBox.warning(self, "API Key 없음", "ANTHROPIC_API_KEY를 설정해주세요.")
            return

        reference = self.reference_text.toPlainText().strip()
        if not reference:
            QMessageBox.warning(self, "입력 오류", "레퍼런스 글을 입력해주세요.")
            return

        self.status_bar.showMessage("구조 분석 중...")
        self.analysis_text.setPlainText("분석 중입니다. 잠시만 기다려주세요...")

        # 분석 스레드 시작
        self.analyze_thread = AnalyzeThread(self.client, reference)
        self.analyze_thread.finished.connect(self.on_analysis_finished)
        self.analyze_thread.error.connect(self.on_analysis_error)
        self.analyze_thread.start()

    def on_analysis_finished(self, result):
        """분석 완료 처리"""
        self.analysis_result = result
        self.analysis_text.setPlainText(result)
        self.status_bar.showMessage("분석 완료!")

    def on_analysis_error(self, error):
        """분석 오류 처리"""
        self.analysis_text.setPlainText("")
        self.status_bar.showMessage("분석 실패")
        QMessageBox.critical(self, "오류", f"분석 중 오류가 발생했습니다:\n{error}")

    def generate_content(self):
        """새 글 생성"""
        if not self.client:
            QMessageBox.warning(self, "API Key 없음", "ANTHROPIC_API_KEY를 설정해주세요.")
            return

        reference = self.reference_text.toPlainText().strip()
        topic = self.topic_input.text().strip()
        keywords = self.keywords_input.text().strip()

        if not reference:
            QMessageBox.warning(self, "입력 오류", "레퍼런스 글을 입력해주세요.")
            return

        if not topic:
            QMessageBox.warning(self, "입력 오류", "주제를 입력해주세요.")
            return

        if not self.analysis_result:
            QMessageBox.warning(self, "분석 필요", "먼저 레퍼런스 글을 분석해주세요.")
            return

        requirements = self.requirements_input.toPlainText().strip()

        self.status_bar.showMessage("글 생성 중...")
        self.generated_text.setPlainText("글을 생성하고 있습니다. 잠시만 기다려주세요...")

        # 생성 스레드 시작
        self.generate_thread = GenerateThread(
            self.client, reference, self.analysis_result,
            topic, keywords, requirements
        )
        self.generate_thread.finished.connect(self.on_generation_finished)
        self.generate_thread.error.connect(self.on_generation_error)
        self.generate_thread.start()

    def on_generation_finished(self, result):
        """글 생성 완료 처리"""
        self.generated_text.setPlainText(result)
        self.status_bar.showMessage("글 생성 완료!")

        # Supabase에 저장
        if self.supabase:
            self.save_to_supabase(result)

    def on_generation_error(self, error):
        """글 생성 오류 처리"""
        self.generated_text.setPlainText("")
        self.status_bar.showMessage("생성 실패")
        QMessageBox.critical(self, "오류", f"글 생성 중 오류가 발생했습니다:\n{error}")

    def save_content(self):
        """생성된 글 저장"""
        content = self.generated_text.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "저장 오류", "저장할 내용이 없습니다.")
            return

        format_option = self.format_combo.currentText()

        if format_option == ".txt":
            file_filter = "Text Files (*.txt)"
            default_ext = ".txt"
        elif format_option == ".md":
            file_filter = "Markdown Files (*.md)"
            default_ext = ".md"
        else:  # HTML
            file_filter = "HTML Files (*.html)"
            default_ext = ".html"
            # HTML 변환 (간단한 변환)
            content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>블로그 글</title>
</head>
<body>
{content.replace(chr(10), '<br>' + chr(10))}
</body>
</html>"""

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "저장 위치 선택",
            "",
            file_filter
        )

        if file_path:
            if not file_path.endswith(default_ext):
                file_path += default_ext

            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.status_bar.showMessage(f"저장 완료: {file_path}")
                QMessageBox.information(self, "저장 완료", f"파일이 저장되었습니다:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"파일을 저장할 수 없습니다:\n{str(e)}")

    def save_to_supabase(self, generated_content):
        """Supabase에 프로젝트 저장"""
        try:
            reference = self.reference_text.toPlainText().strip()
            topic = self.topic_input.text().strip()
            keywords = self.keywords_input.text().strip()
            requirements = self.requirements_input.toPlainText().strip()
            url = self.url_input.text().strip()

            data = {
                "reference_text": reference,
                "reference_url": url if url else None,
                "analysis_result": self.analysis_result,
                "topic": topic,
                "keywords": keywords,
                "requirements": requirements if requirements else None,
                "generated_content": generated_content,
                "status": "completed"
            }

            response = self.supabase.table("blog_projects").insert(data).execute()

            if response.data:
                self.current_project_id = response.data[0]['id']
                print(f"프로젝트 저장 완료: {self.current_project_id}")
        except Exception as e:
            print(f"Supabase 저장 오류: {e}")

    def load_project_history(self):
        """저장된 프로젝트 히스토리 불러오기"""
        try:
            response = self.supabase.table("blog_projects")\
                .select("*")\
                .order("created_at", desc=True)\
                .limit(20)\
                .execute()

            return response.data
        except Exception as e:
            print(f"히스토리 로드 오류: {e}")
            return []

    def reset_all(self):
        """모든 필드 초기화"""
        reply = QMessageBox.question(
            self,
            "초기화 확인",
            "모든 내용을 초기화하시겠습니까?\n작성 중인 내용이 모두 삭제됩니다.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # URL 입력 초기화
            self.url_input.clear()

            # 레퍼런스 텍스트 초기화
            self.reference_text.clear()

            # 분석 결과 초기화
            self.analysis_text.clear()
            self.analysis_result = ""

            # 주제, 키워드, 요구사항 초기화
            self.topic_input.clear()
            self.keywords_input.clear()
            self.requirements_input.clear()

            # 생성된 글 초기화
            self.generated_text.clear()

            # 프로젝트 ID 초기화
            self.current_project_id = None

            # 상태바 메시지
            self.status_bar.showMessage("모든 내용이 초기화되었습니다.")

            QMessageBox.information(self, "초기화 완료", "모든 내용이 초기화되었습니다.")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Fusion 스타일 사용

    window = BlogGeneratorApp()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
