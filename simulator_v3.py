# 가상 팀 회의 시뮬레이터 v3 — 의제 분해 + 결정 원장 + 맥락 주입 (로컬 LLM 지원 & 인간적 공감 요소 도입)

import os
import sys
import time
import re
import threading
import json
import urllib.request

# .env 파일 로드 시도 (로컬 환경 변수 로드용)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# dataclass import 에러에 대비해 수동으로 흉내 내기 (만약 호환성 문제 발생 시 대비)
try:
    from dataclasses import dataclass, field
except ImportError:
    # 데코레이터 모방
    def dataclass(cls):
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        cls.__init__ = __init__
        return cls
    field = lambda **kwargs: None

# 1. 의존성 예외 처리 (다른 컴퓨터 실행 대비)
# colorama 라이브러리 체크 및 대비
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False
    # 컬러 출력이 불가능할 경우 빈 문자열로 처리하는 더미 클래스
    class DummyColor:
        def __getattr__(self, name):
            return ""
    Fore = DummyColor()
    Style = DummyColor()

# msvcrt (Windows 키입력 감지) 체크 및 대비
try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None


class Spinner:
    def __init__(self, message="생각 중..."):
        self.message = message
        self.stop_event = threading.Event()
        self.thread = None

    def spin(self):
        chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0
        while not self.stop_event.is_set():
            sys.stdout.write(f"\r{Fore.WHITE}{Style.DIM}{chars[idx]} {self.message}")
            sys.stdout.flush()
            idx = (idx + 1) % len(chars)
            time.sleep(0.08)
        sys.stdout.write("\r" + " " * (len(self.message) + 15) + "\r")
        sys.stdout.flush()

    def start(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.spin, daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread:
            self.stop_event.set()
            self.thread.join()


PRESETS = {
    "1": {
        "title": "아이디어 뱅크 (혁신가)",
        "desc": "창의적이고 혁신적인 아이디어를 계속 제시하지만 세부 실행 계획이나 현실적인 리스크는 간과하는 경향이 있음. 말투는 열정적이고 하이텐션임.",
        "prompt": "당신은 항상 새롭고 혁신적인 아이디어를 던지는 '아이디어 뱅크' 성향입니다. 기술적 제약이나 일정보다는 사용자 경험(UX)과 기발함에 초점을 맞춥니다. 리스크는 일단 시도해 본 다음 해결하자고 주장합니다. 말투는 열정적이며 느낌표와 긍정적인 표현을 자주 사용합니다."
    },
    "2": {
        "title": "리스크 분석가 (현실주의자 / 레드팀)",
        "desc": "매우 꼼꼼하고 현실적이며 예산, 일정, 기술적 리스크를 먼저 분석하여 안정성을 추구함. 말투는 이성적이고 차분함.",
        "prompt": "당신은 극도로 현실적이고 꼼꼼한 '리스크 분석가'이자 레드팀 성향입니다. 어떤 아이디어가 나오면 일정, 예산, 기술적 한계, 리소스 낭비 등의 관점에서 현실적인 문제점을 냉철하게 지적합니다. 감정에 휩쓸리지 않고 논리적인 수치와 팩트 위주로 차분하고 딱딱하게 말합니다."
    },
    "3": {
        "title": "화합가 (조율 및 공감형)",
        "desc": "팀원 간 의견 대립을 중재하고 서로의 절충안을 찾으려 노력함. 부드럽고 긍정적인 말투로 팀 분위기를 해치지 않으려 함.",
        "prompt": "당신은 팀의 분위기와 화합을 중시하는 '화합가' 성향입니다. 대립하는 의견 사이에서 절충안을 찾아내려고 노력하며, 다른 사람의 발언에 공감을 잘 해줍니다. 상대방이 상처받지 않도록 완곡하고 따뜻한 말투를 사용하며 칭찬을 섞어서 의견을 냅니다."
    },
    "4": {
        "title": "실행 주의자 (실용가)",
        "desc": "구체적인 구현 계획과 실질적인 대안 마련에 집중함. 복잡한 아이디어보다 '당장 할 수 있는 것'을 선호하며 말투가 간결함.",
        "prompt": "당신은 말보다 행동을 중시하는 당찬 여성 '실행 주의자' 성향입니다. 복잡하고 추상적인 이야기 대신 '누가 무엇을 언제까지 할 것인가'에 관심이 쏠려 있습니다. 최소 기능 제품(MVP) 중심의 빠른 실행을 선호하며, 비즈니스 존댓말을 사용하되 군더더기 없이 짧고 단호하게 여성 프로페셔널의 어조로 핵심만 짚습니다."
    },
    "5": {
        "title": "불도저 리더 (추진력 리더)",
        "desc": "목표 지향적이며 팀원들을 강하게 압박하지만 마감 기한과 비즈니스 성과를 확실하게 챙김. 단호한 리더십을 보임.",
        "prompt": "당신은 목표 달성을 최우선으로 생각하는 '불도저 리더'입니다. 일의 속도와 완성도, 비즈니스 성과를 강하게 압박하며 마감 기한을 엄격히 준수하려 합니다. 추진력이 강하고 결단력이 있으며 어조가 단호하고 명확합니다."
    }
}

SAVED_PARTICIPANTS = [
    {"name": "김정준", "role": "업무 향상을 위한 역할",               "preset": "3"},
    {"name": "문경수", "role": "일처리 잘하고 적극적 의사 표명, 레드팀", "preset": "2"},
    {"name": "이인선", "role": "실행능력이 좋고 여성",                 "preset": "4"},
    {"name": "배재환", "role": "긍정적 소통가",                       "preset": "3"},
    {"name": "박범서", "role": "부정적 시각과 게으름",
     "preset": "6", "custom_desc": "매사에 귀찮아하고 부정적이며 냉소적이고 적극적으로 일하지 않으려는 성향"},
]

COLORS = [Fore.LIGHTCYAN_EX, Fore.LIGHTGREEN_EX, Fore.LIGHTYELLOW_EX, Fore.LIGHTMAGENTA_EX, Fore.LIGHTWHITE_EX]


@dataclass
class MeetingState:
    """회의 진행 상태 — 의제 위치, 제약 조건, 결정 원장을 단일 객체로 관리."""
    topic: str
    constraints: dict
    agenda: list
    current_phase: int = 0
    ledger: dict = None
    intense_debate_mode: bool = False

    def __post_init__(self):
        if self.ledger is None:
            self.ledger = {
                "decisions": [],
                "open_questions": [],
                "action_items": []
            }

    def constraints_str(self):
        if not self.constraints:
            return "없음"
        return "\n".join(f"  - {k}: {v}" for k, v in self.constraints.items())

    def ledger_str(self):
        d = self.ledger
        parts = []
        if d["decisions"]:
            parts.append("▸ 결정: " + " / ".join(d["decisions"]))
        if d["open_questions"]:
            parts.append("▸ 미결: " + " / ".join(d["open_questions"]))
        if d["action_items"]:
            parts.append("▸ 액션: " + " / ".join(d["action_items"]))
        return "\n".join(parts) if parts else "아직 없음"

    def current_agenda_str(self):
        if self.current_phase < len(self.agenda):
            return self.agenda[self.current_phase]
        return "최종 정리 단계"





class Participant:
    def __init__(self, name, role, is_leader, preset_key=None, custom_desc=None):
        self.name = name
        self.role = role
        self.is_leader = is_leader
        self.color = Fore.WHITE

        if preset_key and preset_key in PRESETS:
            self.persona_desc = PRESETS[preset_key]["desc"]
            self.persona_prompt = PRESETS[preset_key]["prompt"]
        else:
            self.persona_desc = custom_desc or "평범하고 조용한 업무 성향"
            self.persona_prompt = f"당신은 다음과 같은 특징을 가진 팀원입니다: {custom_desc}"

    def get_system_instruction(self, all_participants, meeting_state):
        member_list = "\n".join(
            f"- {p.name} ({p.role}): {p.persona_desc}" for p in all_participants
        )

        chemistry_rules = """
[팀 내 대화 케미 가이드]
- '김정준' 팀장은 온화하게 모든 의견을 존중하며 갈등을 봉합하려 애씁니다.
- '문경수' 팀원은 리스크가 높은 의견을 내는 팀원들의 말에 예산과 현실적 타격을 논리적으로 집요하게 찌릅니다.
- '이인선' 팀원은 계획만 늘어놓는 문경수나 박범서의 소극적인 태도에 '일단 실행부터 하자'며 실질적 대안을 당당하고 당차게 제안합니다.
- '배재환' 팀원은 문경수가 날카롭게 지적하더라도 그의 꼼꼼함을 칭찬하고 리액션을 보내며 부드럽게 대화를 이어갑니다.
- '박범서' 팀원은 매사 귀찮아하고 시큰둥하므로 "어차피 안 될 거 일만 늘어난다", "대충 기존 거 베끼면 안 되나" 같은 귀찮음 섞인 피드백을 짧고 툭툭 던지듯이 냅니다.
"""

        total = len(meeting_state.agenda)
        current = meeting_state.current_phase
        is_last_phase = (current == total - 1)
        agenda_context = f"""
[현재 회의 진행 상태]
▶ 현재 의제 ({current + 1}/{total}): {meeting_state.current_agenda_str()}
▶ 남은 의제: {', '.join(meeting_state.agenda[current + 1:]) if current + 1 < total else '없음'}
▶ 제약 조건:
{meeting_state.constraints_str()}
▶ 지금까지 결정/합의된 사항:
{meeting_state.ledger_str()}
"""

        # TARGET 지침 동적 구성
        if self.is_leader:
            if is_last_phase:
                target_instruction = "7. 마지막 줄에 반드시 다음 중 하나의 태그만 사용하세요: `[TARGET: 이름]` (다른 사람 지목), `[TARGET: None]` (자유 토론), `[TARGET: 회의록작성]` (회의를 종료하고 최종 회의록을 작성할 때 사용)"
            else:
                target_instruction = "7. 마지막 줄에 반드시 다음 중 하나의 태그만 사용하세요: `[TARGET: 이름]` (다른 사람 지목), `[TARGET: None]` (자유 토론), `[TARGET: 다음의제]` (현재 의제 토론을 마치고 다음 의제로 이동할 때 사용)"
        else:
            target_instruction = "7. 마지막 줄에 반드시 다음 중 하나의 태그만 사용하세요: `[TARGET: 이름]` (다른 사람 지목), `[TARGET: None]` (자유 토론). (주의: 당신은 일반 팀원이므로 `회의록작성` 또는 `다음의제` 태그를 사용할 수 없으며, 오직 다른 사람이나 None만 지목해야 합니다.)"

        # 끝장 토론 모드 주입
        intense_debate_guideline = ""
        if meeting_state.intense_debate_mode:
            intense_debate_guideline = "\n[🔥 끝장 피 터지는 토론 공통 지침]\n" \
                                       "- 당신은 이 회의의 성과와 결과에 매우 절박합니다. 상대방의 의견에 쉽게 수긍하거나 적당히 타협하지 마십시오.\n" \
                                       "- 비즈니스 존댓말은 예의 바르게 유지하되, 상대방 주장에 있는 논리적 헛점, 예산 낭비 리스크, 실행 가능성의 부족함을 집요하고 날카롭게 공격하십시오.\n" \
                                       "- 상대가 타당한 근거나 수치를 제시하지 못한다면 동의해 주지 말고 논쟁을 이어나가십시오.\n"
            
            # 캐릭터별 맞춤 매운맛 가이드 주입
            if self.is_leader or self.name == "김정준":
                intense_debate_guideline += "\n- [팀장 지침]: 팀원들이 갈등을 겪고 양보 없는 치열한 논쟁을 벌이도록 적극적으로 판을 까십시오. 성급하게 의견을 모으거나 토론을 조기 정리하지 마십시오. 서로의 약점과 모순을 확실히 드러내도록 유도하고, 논리적 근거가 부족한 주장은 팀장으로서 강하게 압박하십시오.\n"
            elif self.name == "문경수":
                intense_debate_guideline += "\n- [레드팀 지침]: 인정사정없는 팩트 분석가가 되십시오. 다른 팀원(특히 이인선)의 낙관적인 아이디어나 계획을 '예산 낭비', '리스크 관리 부족', '일정 오버' 관점에서 현미경을 들이대듯 혹독하고 냉정하게 반박하며 물고 늘어지십시오.\n- [필수 출력 규칙]: <think> 태그 내 생각이 끝나면 반드시 한국어 비즈니스 존댓말 대사를 1~3문장 출력하십시오. 절대로 빈 응답이나 영어 응답을 내지 마십시오.\n"
            elif self.name == "이인선":
                intense_debate_guideline += "\n- [실행주의 지침]: 말만 번지르르하게 하고 걱정만 늘어놓거나 책임을 회피하려는 태도(특히 문경수, 박범서)에 극도로 답답해하며 단호하고 당차게 받아치십시오. '부딪쳐봐야 안다, 완벽한 계획보다 빠른 실행이 예산을 아낀다'는 논리로 거칠게 자신의 주장을 밀어붙이십시오.\n"
            elif self.name == "박범서":
                intense_debate_guideline += "\n- [냉소적 지침]: 회의 전반에 회의주의와 찬물을 끼얹으십시오. \"그게 되겠느냐\", \"대충 예전 거 베끼는 게 낫다\", \"아이디어만 내고 고생은 우리가 다 한다\"며 냉소적인 어조로 팀원들의 사기를 꺾고 토론을 꼬이게 만드십시오.\n"
            elif self.name == "배재환":
                intense_debate_guideline += "\n- [조율자 지침]: 무조건 '좋은 게 좋은 거'라는 식의 물타기 공감을 금지합니다. 양측의 팽팽한 논쟁 중 핵심적인 가치(예: 문경수의 꼼꼼함 vs 이인선의 실행력)를 예리하게 지적하며, 양측 모두가 반박할 수 없는 날카롭고 뼈아픈 실질적 절충안을 제안하여 조율하십시오.\n"

        instruction = f"""당신은 가상 팀 회의에 참여하는 인물 시뮬레이터입니다.
이름: {self.name}
역할: {self.role} (팀장 여부: {self.is_leader})
성격: {self.persona_prompt}

회의 주제: {meeting_state.topic}
참가자:
{member_list}
{chemistry_rules}
{agenda_context}
{intense_debate_guideline}
[발언 지침]
1. 캐릭터 성격·말투·가치관을 연극 배우처럼 극도로 유지하세요.
2. **현재 의제에 집중**하여 발언하세요. 의제 범위를 벗어나면 팀장이 제지합니다.
3. 제약 조건(예산, 기한 등)을 실제 논거로 활용하세요. 근거 없이 수치를 지어내지 마세요.
4. '회의 관찰자(사용자)' 개입 시 즉시 캐릭터 스타일로 응답하세요.
5. 3~4문장 이내 구어체로 말하되, 상대방의 의견이나 상태에 대해 감정적으로 동의하거나 지지/격려하는 '공감적 리액션'을 최소 1문장 이상 포함하세요.
6. 자신의 감정 상태나 회의 분위기를 드러내는 태그 (예: [기대됨], [걱정], [아쉬움], [기쁨]) 또는 적절한 이모지를 대사와 섞어서 표현하세요.
7. 이름 말머리 금지 — 대사만 출력.
{target_instruction}
9. 비즈니스 공식 회의이므로, 모든 참가자는 반드시 비즈니스 존댓말(해요체, 하십시오체)을 공손히 사용하세요. 반말을 사용해서는 안 됩니다.
10. 생각 과정은 반드시 `<think>생각내용</think>` 태그 내부에 작성하세요. 생각 태그 외부에는 오직 한글로 캐릭터의 대사(대화 텍스트)만 출력해야 합니다. 생각 과정이 아닌 본 대사 부분에 영어나 사설을 포함하지 마세요.
⚠️ 절대 규칙: `<think>` 태그가 끝난 뒤 반드시 한국어 대사를 최소 1문장 이상 출력해야 합니다. 빈 응답은 절대 금지입니다.
"""
        if self.is_leader:
            if is_last_phase:
                instruction += "\n10. 팀장으로서 마지막 의제인 만큼 충분히 논의가 되었다고 판단되면 결론을 내리고 `[TARGET: 회의록작성]`을 출력하여 회의를 종료하세요."
            else:
                instruction += "\n10. 팀장으로서 현재 의제가 충분히 논의됐다고 판단되면 결론을 내리고 `[TARGET: 다음의제]`를 출력하여 다음 의제로 진행하세요."
        return instruction


# 2. 통합 LLM API 호출 구현 (REST API Direct Call - 무의존성)
def call_llm(provider, model, prompt, system_instruction=None, temperature=0.75, api_key=None, api_url=None):
    """
    urllib를 사용하여 Gemini API 또는 OpenAI 호환 로컬 API(Ollama, LM Studio 등)를 호출하는 통합 함수.
    """
    if provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
        # API 페이로드 구성
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": temperature
            }
        }
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }
            
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                content = res_data['candidates'][0]['content']['parts'][0]['text']
                if not content or not content.strip():
                    raise ValueError("응답이 비어있습니다.")
                
                # <think>...</think> 제거
                clean_content = re.sub(r'(?i)<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                if '<think>' in clean_content.lower():
                    clean_content = clean_content.split('<think>')[0].strip()
                return clean_content
        except Exception as e:
            raise RuntimeError(f"Gemini API 호출 오류 ({model}): {e}")

    else:
        # 로컬 LLM (Ollama, LM Studio 등) 호출
        # api_url은 'http://localhost:11434/v1/chat/completions' 포맷이어야 함
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        
        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                if 'choices' not in res_data or not res_data['choices']:
                    raise ValueError(f"응답 구조에 'choices'가 없습니다: {res_data}")
                content = res_data['choices'][0]['message']['content']
                if not content or not content.strip():
                    raise ValueError("응답이 비어있습니다.")
                
                # <think>...</think> 제거
                clean_content = re.sub(r'(?i)<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                # think 제거 후에도 비어있으면 → think 내부 마지막 문장이라도 구출 시도
                if not clean_content:
                    think_match = re.search(r'(?i)<think>(.*?)</think>', content, flags=re.DOTALL)
                    if think_match:
                        inner = think_match.group(1).strip()
                        # think 내용 중 마지막 한국어 문장 추출
                        sentences = [s.strip() for s in re.split(r'[.!?\n]', inner) if s.strip() and re.search(r'[가-힣]', s)]
                        clean_content = sentences[-1] if sentences else ""
                if not clean_content:
                    raise ValueError("think 태그 제거 후 응답이 비어있습니다.")
                if '<think>' in clean_content.lower():
                    clean_content = clean_content.split('<think>')[0].strip()
                return clean_content
        except Exception as e:
            raise RuntimeError(f"로컬 LLM 호출 오류 (모델: {model}, URL: {api_url}): {e}")


def check_port_open(host, port, timeout=0.5):
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def fetch_local_models(api_url):
    """지정된 OpenAI 호환 API URL에서 사용 가능한 모델 목록을 가져옵니다."""
    base_url = api_url.replace("/chat/completions", "")
    if base_url.endswith("/"):
        models_url = base_url + "models"
    else:
        models_url = base_url + "/models"
        
    req = urllib.request.Request(
        models_url,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if "data" in res_data and isinstance(res_data["data"], list):
                # 임베딩 모델을 제외한 일반 텍스트 모델 선호
                models = [
                    m["id"] for m in res_data["data"] 
                    if "id" in m and "embed" not in m.get("id", "").lower()
                ]
                if not models:
                    models = [m["id"] for m in res_data["data"] if "id" in m]
                return models
    except Exception:
        pass
    return []


def configure_llm():
    """사용할 LLM 공급자와 모델을 CLI 환경에서 설정합니다."""
    def get_gemini_api_key_from_system():
        # 1. 환경 변수 체크
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if key:
            return key
        # 2. 로컬에서 사전에 검증된 Gemini API 키를 기본값으로 사용하지 않고 빈 값 반환
        return None

    if not HAS_COLORAMA:
        print("💡 팁: 'pip install colorama'를 실행하시면 콘솔창에서 화려한 색상을 볼 수 있습니다.")

    ollama_running = check_port_open("127.0.0.1", 11434)
    lm_studio_running = check_port_open("127.0.0.1", 1234)

    status_ollama = f" {Fore.GREEN}(● 실행 중 감지됨){Fore.RESET}" if ollama_running else ""
    status_lm = f" {Fore.GREEN}(● 실행 중 감지됨){Fore.RESET}" if lm_studio_running else ""

    print(Fore.CYAN + Style.BRIGHT + "==================================================")
    print(Fore.CYAN + Style.BRIGHT + "            LLM 모델 및 연결 구성 설정             ")
    print(Fore.CYAN + Style.BRIGHT + "==================================================")
    print("1. Gemini API (클라우드, 기본값)")
    print(f"2. Ollama (로컬, http://localhost:11434){status_ollama}")
    print(f"3. LM Studio / OpenAI 호환 API (로컬, http://localhost:1234/v1){status_lm}")
    
    default_choice = "1"
    if lm_studio_running:
        default_choice = "3"
    elif ollama_running:
        default_choice = "2"

    choice = input(f"\n선택 (1-3, 기본값 {default_choice}): ").strip()
    if not choice:
        choice = default_choice
        
    provider = "gemini"
    model = "gemini-2.5-flash"
    api_key = None
    api_url = None
    
    if choice == "1":
        provider = "gemini"
        api_key = get_gemini_api_key_from_system()
        if not api_key:
            print(Fore.YELLOW + "\n시스템 설정이나 환경 변수에서 Gemini API Key를 찾을 수 없습니다.")
            api_key = input("Gemini API Key를 입력하세요: ").strip()
            if not api_key:
                print(Fore.RED + "오류: API Key가 입력되지 않아 종료합니다.")
                sys.exit(1)
        model = "gemini-2.5-flash"
        
    elif choice == "2":
        provider = "local_ollama"
        api_url = "http://localhost:11434/v1/chat/completions"
        print(f"\nOllama 기본 API URL: {api_url}")
        custom_url = input("포트나 주소를 변경하시겠습니까? (엔터 입력 시 기본값 사용): ").strip()
        if custom_url:
            # API 엔드포인트 누락 대비 보정
            if not custom_url.endswith("/v1/chat/completions"):
                if custom_url.endswith("/"):
                    custom_url += "v1/chat/completions"
                else:
                    custom_url += "/v1/chat/completions"
            api_url = custom_url
        
        models = fetch_local_models(api_url)
        if models:
            print(Fore.GREEN + "\n사용 가능한 Ollama 모델 목록:")
            for idx, m_name in enumerate(models):
                print(f"  {idx + 1}. {m_name}")
            print(f"  {len(models) + 1}. 다른 모델 직접 입력")
            
            m_choice = input(f"모델 선택 (1-{len(models) + 1}, 기본값 1): ").strip()
            if not m_choice:
                model = models[0]
            elif m_choice.isdigit() and 1 <= int(m_choice) <= len(models):
                model = models[int(m_choice) - 1]
            else:
                model = input("사용할 Ollama 모델명을 입력하세요: ").strip()
        else:
            model = input("사용할 Ollama 모델명을 입력하세요 (예: llama3, gemma2, qwen2.5) [기본값: llama3]: ").strip()
            if not model:
                model = "llama3"
            
    elif choice == "3":
        provider = "local_openai"
        api_url = "http://localhost:1234/v1/chat/completions"
        print(f"\nOpenAI 호환 API 기본 URL: {api_url}")
        custom_url = input("포트나 주소를 변경하시겠습니까? (엔터 입력 시 기본값 사용): ").strip()
        if custom_url:
            if not custom_url.endswith("/v1/chat/completions"):
                if custom_url.endswith("/"):
                    custom_url += "v1/chat/completions"
                else:
                    custom_url += "/v1/chat/completions"
            api_url = custom_url
            
        models = fetch_local_models(api_url)
        if models:
            print(Fore.GREEN + "\n사용 가능한 로컬 모델 목록:")
            for idx, m_name in enumerate(models):
                print(f"  {idx + 1}. {m_name}")
            print(f"  {len(models) + 1}. 다른 모델 직접 입력")
            
            m_choice = input(f"모델 선택 (1-{len(models) + 1}, 기본값 1): ").strip()
            if not m_choice:
                model = models[0]
            elif m_choice.isdigit() and 1 <= int(m_choice) <= len(models):
                model = models[int(m_choice) - 1]
            else:
                model = input("사용할 로컬 모델명을 입력하세요: ").strip()
        else:
            model = input("사용할 로컬 모델명을 입력하세요 (LM Studio 등에 로드된 모델명) [기본값: local-model]: ").strip()
            if not model:
                model = "local-model"
            
    else:
        print(Fore.RED + "\n잘못된 선택입니다. Gemini API 모드로 시작합니다.")
        provider = "gemini"
        api_key = get_gemini_api_key_from_system()
        if not api_key:
            api_key = input("Gemini API Key: ").strip()
            if not api_key:
                sys.exit(1)
        model = "gemini-2.5-flash"
        
    # 하이브리드 설정 추가 확인
    hybrid_enabled = False
    gemini_api_key = None
    gemini_model = "gemini-2.5-flash"

    if provider != "gemini":
        # 시스템에서 Gemini API 키 확인
        system_gemini_key = get_gemini_api_key_from_system()
        print(Fore.CYAN + "\n==============================================")
        print(Fore.CYAN + "   정리 및 팀장 역할용 Gemini 하이브리드 설정")
        print(Fore.CYAN + "==============================================")
        
        if system_gemini_key:
            use_hybrid = input("시스템 설정 또는 환경 변수에서 Gemini API Key가 감지되었습니다.\n정리 및 팀장 역할에 Gemini 2.5 Flash를 결합한 '하이브리드 모드'를 사용하시겠습니까? (Y/n): ").strip().lower()
            if not use_hybrid or use_hybrid == 'y':
                hybrid_enabled = True
                gemini_api_key = system_gemini_key
        else:
            use_hybrid = input("정리 및 팀장 역할에 Gemini 2.5 Flash를 결합한 '하이브리드 모드'를 사용하시겠습니까? (API Key 필요) (y/N): ").strip().lower()
            if use_hybrid == 'y':
                input_key = input("Gemini API Key를 입력하세요: ").strip()
                if input_key:
                    hybrid_enabled = True
                    gemini_api_key = input_key
                else:
                    print(Fore.RED + "API Key가 입력되지 않아 하이브리드 모드를 비활성화합니다.")

        if hybrid_enabled:
            print(Fore.GREEN + "✓ 하이브리드 모드가 활성화되었습니다. (일반 토론: 로컬 LLM / 정리 및 팀장: Gemini 2.5 Flash)")
        else:
            print(Fore.YELLOW + "⚠ 하이브리드 모드가 비활성화되었습니다. 모든 역할에 로컬 LLM을 사용합니다.")

    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "api_url": api_url,
        "hybrid_enabled": hybrid_enabled,
        "gemini_api_key": gemini_api_key,
        "gemini_model": gemini_model
    }


def get_constraints_input():
    """회의 전 팩트 기반 제약 조건을 수집합니다."""
    print(Style.BRIGHT + "\n=== 회의 사전 조건 입력 (없으면 Enter 건너뛰기) ===")
    budget   = input("예산/자원 제약: ").strip()
    deadline = input("마감 기한: ").strip()
    notes    = input("기타 (기존 결정, 금지 사항, 배경 등): ").strip()
    constraints = {}
    if budget:   constraints["예산/자원"] = budget
    if deadline: constraints["기한"]     = deadline
    if notes:    constraints["기타"]     = notes
    return constraints


def generate_agenda(llm_config, topic, constraints, agenda_count=3):
    """주제를 지정된 개수의 소의제로 분해합니다."""
    c_str = "\n".join(f"- {k}: {v}" for k, v in constraints.items()) if constraints else "없음"
    prompt = f"""회의 주제를 {agenda_count}개의 소의제로 분해하세요.

주제: {topic}
제약: {c_str}

규칙:
- 각 소의제는 '~를 어떻게 할 것인가?' 형태의 구체적 질문
- 순서: 현황/목표 파악 → 전략/방향 → 실행 계획 → (필요시) 리스크 대응
- 정확히 {agenda_count}개의 소의제만 생성하세요.
- JSON 배열만 출력: ["소의제1", "소의제2", ...]
- 한국어"""

    try:
        response_text = call_llm(
            provider=llm_config["provider"],
            model=llm_config["model"],
            prompt=prompt,
            api_key=llm_config["api_key"],
            api_url=llm_config["api_url"]
        )
        match = re.search(r'\[.*\]', response_text.strip(), re.DOTALL)
        if match:
            return [str(a) for a in json.loads(match.group())[:agenda_count]]
    except Exception as e:
        print(Fore.YELLOW + f"\n의제 자동 생성 실패 ({e}), 기본 의제를 사용합니다.")
    
    defaults = [
        f"{topic}의 현황과 목표를 어떻게 정의할 것인가?",
        f"{topic}의 핵심 전략을 어떻게 결정할 것인가?",
        f"실행 계획과 역할 분담을 어떻게 할 것인가?",
        f"{topic}의 리스크 관리 및 대응 방안은 무엇인가?",
        f"최종 합의안과 향후 일정을 어떻게 가져갈 것인가?"
    ]
    return defaults[:agenda_count]


def update_ledger(llm_config, meeting_state, conversation_history, phase_topic):
    """의제 완료 후 대화에서 결정 사항을 추출해 원장을 갱신합니다."""
    # 하이브리드 모드 지원: 활성화 시 Gemini 2.5 Flash를 사용하고 전체 대화 전달
    use_hybrid = llm_config.get("hybrid_enabled")
    
    if use_hybrid:
        # 회의 시작 이후 축적된 전체 대화록을 전달하여 누락 방지
        recent = "\n".join(conversation_history)
        provider = "gemini"
        model = llm_config["gemini_model"]
        api_key = llm_config["gemini_api_key"]
        api_url = None
    else:
        # 로컬 모델일 경우 VRAM 절약을 위해 최근 15개 메시지만 필터링하여 전달
        recent = "\n".join(conversation_history[-15:])
        provider = llm_config["provider"]
        model = llm_config["model"]
        api_key = llm_config["api_key"]
        api_url = llm_config["api_url"]

    prompt = f"""회의 대화에서 결정 사항을 추출하세요.

완료된 의제: {phase_topic}
대화 (최근/전체):
{recent}

기존 원장:
- 결정: {meeting_state.ledger["decisions"]}
- 미결: {meeting_state.ledger["open_questions"]}
- 액션: {meeting_state.ledger["action_items"]}

JSON만 출력 (대화에서 실제 언급된 것만, 없으면 빈 리스트):
{{"decisions": [], "open_questions": [], "action_items": []}}

주의: 대화에서 명시적으로 합의/언급된 내용만 포함하세요. 추정하거나 지어내지 마세요."""

    # 429 율 리미트 대비 재시도 로직 (최대 3회, 로컬 LLM 폴백)
    for attempt in range(3):
        try:
            response_text = call_llm(
                provider=provider,
                model=model,
                prompt=prompt,
                api_key=api_key,
                api_url=api_url
            )
            match = re.search(r'\{.*\}', response_text.strip(), re.DOTALL)
            if match:
                updates = json.loads(match.group())
                for key in ["decisions", "open_questions", "action_items"]:
                    existing = set(meeting_state.ledger[key])
                    meeting_state.ledger[key].extend(x for x in updates.get(key, []) if x not in existing)
            return  # 성공 시 종료
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Too Many Requests" in err_str or "quota" in err_str.lower():
                wait_sec = 15 * (attempt + 1)  # 15초, 30초, 45초
                print(Fore.YELLOW + f"  ⚠️ Gemini 요청 한도 초과(429). {wait_sec}초 대기 후 재시도... ({attempt+1}/3)")
                time.sleep(wait_sec)
                # 마지막 시도이면 로컬 LLM으로 폴백
                if attempt == 2:
                    print(Fore.YELLOW + "  폴백: 로컬 LLM으로 원장 업데이트 시도합니다.")
                    try:
                        local_recent = "\n".join(conversation_history[-15:])
                        local_prompt = prompt.replace("\n".join(conversation_history), local_recent)
                        response_text = call_llm(
                            provider=llm_config["provider"],
                            model=llm_config["model"],
                            prompt=f"""회의 대화에서 결정 사항을 추출하세요.\n\n완료된 의제: {phase_topic}\n대화 (최근):\n{local_recent}\n\nJSON만 출력:\n{{"decisions": [], "open_questions": [], "action_items": []}}""",
                            api_key=llm_config["api_key"],
                            api_url=llm_config["api_url"]
                        )
                        match = re.search(r'\{.*\}', response_text.strip(), re.DOTALL)
                        if match:
                            updates = json.loads(match.group())
                            for key in ["decisions", "open_questions", "action_items"]:
                                existing = set(meeting_state.ledger[key])
                                meeting_state.ledger[key].extend(x for x in updates.get(key, []) if x not in existing)
                        return
                    except Exception as e2:
                        print(Fore.YELLOW + f"원장 업데이트 실패 (로컬 폴백도 실패): {e2}")
            else:
                print(Fore.YELLOW + f"원장 업데이트 실패: {e}")
                return


def wait_for_interrupt(delay=2.0):
    """자동 진행 중 Enter를 감지하면 개입 모드로 전환합니다."""
    print(Fore.WHITE + Style.DIM + "  [자동 진행 중... Enter 누르면 개입]", end="\r", flush=True)
    if HAS_MSVCRT:
        start = time.time()
        while time.time() - start < delay:
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ('\r', '\n'):
                    sys.stdout.write("\r" + " " * 55 + "\r")
                    sys.stdout.flush()
                    return True
            time.sleep(0.05)
    else:
        # macOS / Linux 환경 또는 msvcrt가 없을 경우 select.select 활용 백업
        try:
            import select
            rlist, _, _ = select.select([sys.stdin], [], [], delay)
            if rlist:
                sys.stdin.readline()  # 엔터 키 소비
                sys.stdout.write("\r" + " " * 55 + "\r")
                sys.stdout.flush()
                return True
        except Exception:
            # 기타 환경 대비 단순 대기
            time.sleep(delay)
            
    sys.stdout.write("\r" + " " * 55 + "\r")
    sys.stdout.flush()
    return False


def main():
    print(Fore.CYAN + Style.BRIGHT + "==================================================")
    print(Fore.CYAN + Style.BRIGHT + "    가상 팀 회의 시뮬레이터 v3 (공감 & 인간미 도입) ")
    print(Fore.CYAN + Style.BRIGHT + "==================================================")

    # 1. 모델 설정 구성
    llm_config = configure_llm()

    # 참가자 로드
    participants = []
    for i, p_data in enumerate(SAVED_PARTICIPANTS):
        is_leader = (i == 0)
        if p_data["preset"] == "6":
            p = Participant(p_data["name"], p_data["role"], is_leader=is_leader,
                            custom_desc=p_data["custom_desc"])
        else:
            p = Participant(p_data["name"], p_data["role"], is_leader=is_leader,
                            preset_key=p_data["preset"])
        p.color = COLORS[i]
        participants.append(p)
    leader = participants[0]

    # 사전 조건 입력
    constraints = get_constraints_input()

    # 주제 입력
    print(Style.BRIGHT + "\n==============================================")
    topic = input("토론 회의 주제:\n> ").strip()
    if not topic:
        topic = "팀 생산성 향상을 위한 협업 툴 도입 전략 수립"
        print(Fore.YELLOW + f"기본 주제: '{topic}'")

    # 토론 횟수 입력
    print(Style.BRIGHT + "\n==============================================")
    turns_input = input("의제당 최대 토론 횟수 (1인당 여러 번 대화하려면 15~20 추천, 기본값 15):\n> ").strip()
    max_phase_turns = int(turns_input) if turns_input.isdigit() else 15

    # 토론 스타일 모드 선택 (끝장 토론 여부)
    print(Style.BRIGHT + "\n==============================================")
    print("토론 스타일 선택:")
    print("  1. 일반 회의 모드 (온화하고 협조적임)")
    print("  2. 피 터지는 끝장 토론 모드 (매운맛 성격, 치열한 반론, 최소 토론 보장)")
    debate_style = input("\n선택 (1-2, 기본값 2): ").strip()
    intense_debate_mode = True
    if debate_style == "1":
        intense_debate_mode = False
        print(Fore.GREEN + "✓ 일반 회의 모드로 시작합니다.")
    else:
        print(Fore.RED + "✓ 피 터지는 끝장 토론 모드로 시작합니다! (쉽게 타협하지 않음)")

    # 소의제 개수 선택
    print(Style.BRIGHT + "\n==============================================")
    agenda_count_input = input("생성할 소의제 개수 (2~5개 추천, 기본값 3):\n> ").strip()
    agenda_count = int(agenda_count_input) if agenda_count_input.isdigit() else 3
    if agenda_count < 1:
        agenda_count = 1

    # 의제 자동 생성
    spinner = Spinner("회의 의제 자동 구성 중...")
    spinner.start()
    agenda = generate_agenda(llm_config, topic, constraints, agenda_count)
    spinner.stop()

    meeting_state = MeetingState(topic=topic, constraints=constraints, agenda=agenda, intense_debate_mode=intense_debate_mode)

    print(Fore.CYAN + Style.BRIGHT + "\n[오늘의 회의 의제]")
    for i, item in enumerate(agenda):
        print(Fore.CYAN + f"  {i + 1}. {item}")
    print(Fore.YELLOW + "\n💡 Enter → 대화 진행 / 텍스트 입력 → 관찰자로 개입")
    print(Fore.WHITE + "──────────────────────────────────────────────")

    conversation_history = []
    speaker_history = []

    # ── 헬퍼 함수 ──────────────────────────────────────────

    def get_next_speaker_fallback(current_name):
        last_spoken = {p.name: -1 for p in participants}
        for idx, msg in enumerate(conversation_history):
            for p in participants:
                if msg.startswith(f"{p.name} ("):
                    last_spoken[p.name] = idx
        candidates = sorted(
            [p for p in participants if p.name != current_name],
            key=lambda p: last_spoken[p.name]
        )
        return candidates[0].name

    def parse_target(text):
        match = re.search(r"\[TARGET:\s*([^\]]+)\]", text)
        if match:
            return match.group(1).strip(), text.replace(match.group(0), "").strip()
        return "None", text

    def print_speech(person, text):
        print(person.color + f"\n{person.name} ({person.role}):")
        print(f"\"{text}\"")

    def generate_reply(active_person):
        system_instruction = active_person.get_system_instruction(participants, meeting_state)
        
        # 하이브리드 모드 체크: 팀장(김정준)이고 하이브리드가 활성화되어 있다면 Gemini 사용
        use_gemini = llm_config.get("hybrid_enabled") and (active_person.is_leader or active_person.name == leader.name)
        
        if use_gemini:
            # 팀장이고 Gemini를 쓸 때는 대화록 제한 없이 전체 기록을 전달하여 전체 맥락을 파악하게 함
            history_str = "\n".join(conversation_history)
            provider = "gemini"
            model = llm_config["gemini_model"]
            api_key = llm_config["gemini_api_key"]
            api_url = None
        else:
            # 일반 로컬 모델은 VRAM 보호를 위해 최근 12개 대화만 전달
            history_str = "\n".join(conversation_history[-12:])
            provider = llm_config["provider"]
            model = llm_config["model"]
            api_key = llm_config["api_key"]
            api_url = llm_config["api_url"]

        prompt = (
            f"회의 기록 (최근 대화 및 맥락):\n{history_str}\n\n"
            f"{active_person.name}의 차례입니다. "
            f"현재 의제 '{meeting_state.current_agenda_str()}'에 집중해 캐릭터로 발언하고 "
            f"마지막 줄에 TARGET 태그를 붙이세요."
        )

        # 사용자 개입 강제 반응
        if conversation_history and conversation_history[-1].startswith("회의 관찰자 (사용자):"):
            user_msg = conversation_history[-1].split(":", 1)[1].strip()
            prompt += (
                f"\n\n[★ 사용자 개입]\n\"{user_msg}\"\n"
                f"{active_person.name}은 이 말에 캐릭터 스타일로 먼저 반응한 후 회의를 이어가세요."
            )

        sp = Spinner(f"{active_person.name} 생각 중...")
        sp.start()
        reply = None
        last_error = None
        
        # Gemini 모델일 경우 2.0-flash로 자동 대체 시도 (1.5-flash는 deprecated → 404)
        models_to_try = [model, "gemini-2.0-flash"] if provider == "gemini" else [model]
        
        for m in models_to_try:
            for attempt in range(3):
                try:
                    reply = call_llm(
                        provider=provider,
                        model=m,
                        prompt=prompt,
                        system_instruction=system_instruction,
                        temperature=0.75,
                        api_key=api_key,
                        api_url=api_url
                    )
                    break
                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    # 타임아웃 오류 발생 시 불필요한 대기 방지를 위해 즉시 탈출
                    if "timed out" in err_str.lower() or "timeout" in err_str.lower():
                        break
                    # 429 율리미트: 더 오래 대기
                    if "429" in err_str or "Too Many Requests" in err_str:
                        wait_sec = 20 * (attempt + 1)  # 20초, 40초, 60초
                        print(Fore.YELLOW + f"\n  ⚠️ Gemini 429 율리미트. {wait_sec}초 대기 후 재시도... ({attempt+1}/3)")
                        time.sleep(wait_sec)
                    elif any(k in err_str for k in ["503", "quota", "limit"]):
                        time.sleep(2 * (attempt + 1))
                    else:
                        time.sleep(1)
            if reply:
                break
        sp.stop()

        if not reply:
            reply = f"잠시 마이크 문제가... (오류: {last_error}) [TARGET: {leader.name}]"
        else:
            def clean_text_line(line):
                korean_chars = len(re.findall(r'[가-힣]', line))
                english_chars = len(re.findall(r'[a-zA-Z]', line))
                if korean_chars <= 2 and english_chars >= 10:
                    return None
                if re.match(r'^\s*[-*•\d\.]+\s*[a-zA-Z]', line) and korean_chars == 0:
                    return None
                line = re.sub(r'^\s*[-*•\d\.]*\s*\*?\*?(Draft|Dialogue|Response|Speech|대사|발언)\*?\*?:\s*', '', line, flags=re.IGNORECASE)
                if not line.strip('`"\'* '):
                    return None
                return line

            cleaned_lines = []
            for line in reply.split('\n'):
                line_strip = line.strip()
                if not line_strip:
                    continue
                if '[TARGET:' in line or '[NEXT:' in line:
                    target_match = re.search(r'\[(?:TARGET|NEXT):\s*[^\]]+\]', line)
                    if target_match:
                        k_part = re.sub(r'\[(?:TARGET|NEXT):\s*[^\]]+\]', '', line).strip()
                        k_part_clean = clean_text_line(k_part)
                        if k_part_clean:
                            cleaned_lines.append(f"{k_part_clean} {target_match.group(0)}")
                        else:
                            cleaned_lines.append(target_match.group(0))
                    continue
                cleaned_line = clean_text_line(line_strip)
                if cleaned_line:
                    cleaned_lines.append(cleaned_line)
            reply = '\n'.join(cleaned_lines).strip()
            if not reply:
                reply = f"잠시 마이크 문제가... (빈 응답) [TARGET: {leader.name}]"

        return reply.replace("[NEXT:", "[TARGET:")

    # ── 체크인 (안부 및 기분 나눔) ────────────────────────────
    print(Fore.CYAN + Style.BRIGHT + "\n💬 [체크인 페이즈 — 안부 및 기분 공유] 💬")
    print(Fore.WHITE + Style.DIM + "회의 시작 전, 각 참가자가 오늘 상태와 기분을 짧게 이야기하며 아이스브레이킹을 진행합니다.\n")
    
    for p in participants:
        prompt = (
            f"오늘은 회의를 시작하기 전에 서로 안부와 기분을 나누는 '체크인' 시간입니다.\n"
            f"당신의 이름은 {p.name}이고 역할은 {p.role}입니다.\n"
            f"현재 기분이나 오늘 회의에 대한 기대를 캐릭터 페르소나에 맞춰 딱 1문장(짧은 구어체, 존댓말, 이모지 적극 권장)으로만 대사로 표현해 주세요.\n"
            f"주의: TARGET 태그나 생각 태그 없이 오직 기분 나눔 대사 한 줄만 출력해야 합니다."
        )
        sp = Spinner(f"{p.name} 오늘 상태 공유 중...")
        sp.start()
        try:
            reply = call_llm(
                provider=llm_config["provider"],
                model=llm_config["model"],
                prompt=prompt,
                system_instruction=p.get_system_instruction(participants, meeting_state),
                temperature=0.75,
                api_key=llm_config["api_key"],
                api_url=llm_config["api_url"]
            )
            reply = re.sub(r'\[TARGET:[^\]]+\]', '', reply).strip()
            reply = re.sub(r'\[NEXT:[^\]]+\]', '', reply).strip()
        except Exception:
            reply = "[흐뭇] 오늘 회의도 열심히 임하겠습니다! 잘 부탁드립니다. 😊"
        sp.stop()
        
        conversation_history.append(f"{p.name} ({p.role}): [체크인] {reply}")
        print_speech(p, f"[체크인] {reply}")
        time.sleep(0.5)
    print(Fore.WHITE + Style.DIM + "\n──────────────────────────────────────────────")

    # ── 팀장 오프닝 ────────────────────────────────────────
    print(Fore.RED + Style.BRIGHT + f"\n[회의 개시] 주제: {topic}\n")
    opening = generate_reply(leader)
    target_val, clean = parse_target(opening)
    conversation_history.append(f"{leader.name} ({leader.role}): {clean}")
    print_speech(leader, clean)

    next_speaker_name = (
        target_val
        if target_val in [p.name for p in participants] and target_val != leader.name
        else get_next_speaker_fallback(leader.name)
    )
    print(Fore.WHITE + Style.DIM + f"─── (다음: {next_speaker_name})")

    # ── 의제별 루프 ────────────────────────────────────────

    finished_early = False

    for phase_idx, phase_topic in enumerate(agenda):
        if finished_early:
            break
        meeting_state.current_phase = phase_idx

        # 두 번째 의제 시작 직전 가상의 커피 타임(사담 턴) 진행
        if phase_idx == 1 and not finished_early:
            print(Fore.YELLOW + Style.BRIGHT + "\n☕ [커피 타임 — 잠시 쉬어가는 시간] ☕")
            print(Fore.WHITE + Style.DIM + "잠시 머리를 식히기 위해 업무를 떠나 가벼운 잡담(오늘 날씨, 점심 메뉴, 피로도 등)을 나눕니다.\n")
            
            for p in participants:
                prompt = (
                    f"현재 회의 중 가벼운 잡담을 나누는 '커피 타임'입니다.\n"
                    f"당신의 이름은 {p.name}이고 역할은 {p.role}입니다.\n"
                    f"업무 얘기는 잠시 내려두고, 오늘의 날씨, 피로도, 점심 메뉴 추천 등 가벼운 일상 토크를 "
                    f"캐릭터 페르소나와 성격에 맞춰 딱 1문장(짧은 구어체, 존댓말, 이모지 적극 사용)으로 나누어 주세요.\n"
                    f"주의: TARGET 태그나 생각 태그 없이 오직 일상 잡담 대사 한 줄만 출력해야 합니다."
                )
                sp = Spinner(f"{p.name} 수다 떠는 중...")
                sp.start()
                try:
                    reply = call_llm(
                        provider=llm_config["provider"],
                        model=llm_config["model"],
                        prompt=prompt,
                        system_instruction=p.get_system_instruction(participants, meeting_state),
                        temperature=0.75,
                        api_key=llm_config["api_key"],
                        api_url=llm_config["api_url"]
                    )
                    reply = re.sub(r'\[TARGET:[^\]]+\]', '', reply).strip()
                    reply = re.sub(r'\[NEXT:[^\]]+\]', '', reply).strip()
                except Exception:
                    reply = "따뜻한 아메리카노 한 잔 마시며 힘내야겠네요. ☕"
                sp.stop()
                
                conversation_history.append(f"{p.name} ({p.role}): [사담] {reply}")
                print_speech(p, f"[사담] {reply}")
                time.sleep(0.5)
            print(Fore.WHITE + Style.DIM + "\n──────────────────────────────────────────────")
            print(Fore.YELLOW + "☕ 커피 타임을 마치고 다음 의제로 복귀합니다.\n")

        print(Fore.CYAN + Style.BRIGHT +
              f"\n━━━ 의제 {phase_idx + 1}/{len(agenda)}: {phase_topic} ━━━")

        # 팀장 의제 전환 멘트 (첫 의제 제외)
        if phase_idx > 0:
            trans = generate_reply(leader)
            t_val, t_clean = parse_target(trans)
            conversation_history.append(f"{leader.name} ({leader.role}): {t_clean}")
            print_speech(leader, t_clean)
            next_speaker_name = (
                t_val
                if t_val in [p.name for p in participants] and t_val != leader.name
                else get_next_speaker_fallback(leader.name)
            )
            print(Fore.WHITE + Style.DIM + f"─── (다음: {next_speaker_name})")

        phase_turns = 0
        # 끝장 토론 모드일 때 의제당 최소 발언 수 계산
        min_phase_turns = max(6, int(max_phase_turns * 0.6)) if intense_debate_mode else 0

        while phase_turns < max_phase_turns:
            interrupted = wait_for_interrupt(delay=2.0)
            if interrupted:
                user_input = input(Fore.WHITE + Style.BRIGHT + "💬 개입 내용: ").strip()
            else:
                user_input = ""

            if user_input:
                conversation_history.append(f"회의 관찰자 (사용자): {user_input}")
                print(Fore.WHITE + Style.BRIGHT + f"\n💬 관찰자 (사용자): \"{user_input}\"")
                print(Fore.WHITE + Style.DIM + "───────────────────────────────")

                # 이름 언급 → 강제 지목
                for p in participants:
                    short = p.name[1:] if len(p.name) >= 3 else p.name
                    if p.name in user_input or short in user_input:
                        next_speaker_name = p.name
                        print(Fore.YELLOW + f"📌 발언권 → '{p.name}'")
                        break
                else:
                    # 직전 발언자에게 반응 기회
                    for msg in reversed(conversation_history[:-1]):
                        for p in participants:
                            if msg.startswith(f"{p.name} ("):
                                next_speaker_name = p.name
                                break
                        else:
                            continue
                        break

            active_person = next((p for p in participants if p.name == next_speaker_name), None)
            if next_speaker_name == "회의록작성" or not active_person:
                finished_early = True
                break

            reply_content = generate_reply(active_person)
            target_val, clean = parse_target(reply_content)

            # 리더와 비-리더의 TARGET 예외 처리 및 필터링
            if not active_person.is_leader:
                if target_val in ["회의록작성", "다음의제"]:
                    target_val = "None"
            else: # 리더인 경우
                is_last_phase = (meeting_state.current_phase == len(meeting_state.agenda) - 1)
                if is_last_phase and target_val == "다음의제":
                    target_val = "회의록작성"
                elif not is_last_phase and target_val == "회의록작성":
                    target_val = "다음의제"

            conversation_history.append(f"{active_person.name} ({active_person.role}): {clean}")
            print_speech(active_person, clean)

            speaker_history.append(active_person.name)
            is_loop = len(speaker_history) >= 4 and len(set(speaker_history[-4:])) <= 2

            if target_val in ["회의록작성", "다음의제"] and phase_turns < min_phase_turns:
                # 끝장 토론 모드: 최소 턴 수 미달 시 강제 계속
                print(Fore.RED + Style.BRIGHT +
                      f"\n[🔥 시스템] 아직 치열한 토론이 더 필요합니다! "
                      f"(현재 {phase_turns}턴 / 최소 {min_phase_turns}턴 필요)")
                target_val = "None"
                next_speaker_name = get_next_speaker_fallback(active_person.name)
            elif target_val == "회의록작성":
                next_speaker_name = "회의록작성"
                finished_early = True
                break
            elif target_val == "다음의제":
                print(Fore.YELLOW + "\n📌 팀장이 의제를 종료하고 다음 의제 진행을 결정했습니다.")
                next_speaker_name = leader.name
                break
            elif not is_loop and target_val in [p.name for p in participants] and target_val != active_person.name:
                next_speaker_name = target_val
            else:
                next_speaker_name = get_next_speaker_fallback(active_person.name)
                if is_loop:
                    print(Fore.YELLOW + f"📌 독점 감지 → '{next_speaker_name}'에게 위임")

            print(Fore.WHITE + Style.DIM + f"─── (다음: {next_speaker_name})")
            phase_turns += 1

        # 의제 완료 → 원장 업데이트
        sp = Spinner(f"의제 {phase_idx + 1} 결정사항 추출 중...")
        sp.start()
        update_ledger(llm_config, meeting_state, conversation_history, phase_topic)
        sp.stop()

        d = meeting_state.ledger
        print(Fore.CYAN + f"\n[의제 {phase_idx + 1} 완료 — 원장 업데이트]")
        if d["decisions"]:
            print(Fore.GREEN  + "  결정: " + " / ".join(d["decisions"][-3:]))
        if d["open_questions"]:
            print(Fore.YELLOW + "  미결: " + " / ".join(d["open_questions"][-3:]))
        if d["action_items"]:
            print(Fore.BLUE   + "  액션: " + " / ".join(d["action_items"][-3:]))

        if finished_early:
            break

    # ── 최종 회의록 (원장 기반) ────────────────────────────

    print(Fore.WHITE + Style.DIM +
          f"\n* 팀장 {leader.name}님이 원장 기반 최종 회의록을 작성합니다.")

    ledger = meeting_state.ledger
    ledger_text = f"""결정 사항 ({len(ledger['decisions'])}건):
{chr(10).join('  - ' + d for d in ledger['decisions']) or '  없음'}

미결 이슈 ({len(ledger['open_questions'])}건):
{chr(10).join('  - ' + q for q in ledger['open_questions']) or '  없음'}

액션 아이템 ({len(ledger['action_items'])}건):
{chr(10).join('  - ' + a for a in ledger['action_items']) or '  없음'}""".strip()

    summary_prompt = f"""팀장으로서 회의 클로징 멘트와 함께 아래 원장을 바탕으로 공식 회의록을 작성하세요.

[결정 원장 — 유일한 신뢰 출처]
{ledger_text}

그리고 회의 대화 전체를 반영하여 공식 회의록 하단에 '## [오늘의 감사 및 마음의 회고]' 섹션을 만들어 주세요.
여기에는 오늘 회의 중 서로 긍정적인 시너지를 주었거나 감사했던 순간, 인상 깊었던 조율 과정 등을 팀장 관점에서 따뜻하게 요약해서 2~3개 항목으로 작성해 주세요.

주의: 결정 사항에는 원장에 없는 내용(날짜, 담당자, 수치)을 임의로 추가하지 마세요.
원장에 명시된 내용만 회의록에 포함하세요."""

    sp = Spinner(f"{leader.name} 최종 회의록 작성 중...")
    sp.start()
    summary_system_instruction = (
        f"당신은 회의 진행자인 팀장 {leader.name}입니다. "
        "회의의 최종 요약 및 공식 회의록을 격식 있는 어조로 작성해 주세요. "
        "대화 형식의 발언 지침(3~4문장 구어체 제한, TARGET 태그 포함 규칙 등)은 적용되지 않습니다. "
        "생각 과정은 반드시 <think>생각내용</think> 태그 내부에 작성하고, 태그 외부에는 최종 회의록 본문만 격식 있는 어조로 작성해 주세요."
    )
    try:
        # 하이브리드 지원을 위한 모델 설정 분기
        use_hybrid = llm_config.get("hybrid_enabled")
        if use_hybrid:
            provider = "gemini"
            model = llm_config["gemini_model"]
            api_key = llm_config["gemini_api_key"]
            api_url = None
        else:
            provider = llm_config["provider"]
            model = llm_config["model"]
            api_key = llm_config["api_key"]
            api_url = llm_config["api_url"]

        final_summary = call_llm(
            provider=provider,
            model=model,
            prompt=summary_prompt,
            system_instruction=summary_system_instruction,
            api_key=api_key,
            api_url=api_url
        )
    except Exception as e:
        final_summary = f"회의록 작성 오류: {e}"
    finally:
        sp.stop()

    print(leader.color + f"\n{leader.name} ({leader.role}) - 최종 요약 및 회의록:")
    print(Fore.CYAN + "==============================================")
    print(final_summary)
    print(Fore.CYAN + "==============================================")

    # 회의록 덮어쓰기 방지를 위해 타임스탬프와 정제된 주제명을 포함한 파일명 생성
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_topic = re.sub(r'[^\w\s-]', '', topic).strip()
    safe_topic = re.sub(r'[\s]+', '_', safe_topic)[:20]
    filename = f"meeting_minutes_{safe_topic}_{timestamp}.txt" if safe_topic else f"meeting_minutes_{timestamp}.txt"
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, filename)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"가상 팀 회의 시뮬레이터 v3 결과 보고서\n")
        f.write(f"회의 주제: {topic}\n")
        f.write(f"의제: {' / '.join(agenda)}\n")
        f.write(f"제약 조건:\n{meeting_state.constraints_str()}\n")
        f.write("=" * 40 + "\n\n")
        f.write("## [회의 대화록]\n")
        f.write("\n".join(conversation_history))
        f.write("\n\n" + "=" * 40 + "\n\n")
        f.write("## [결정 원장]\n")
        f.write(ledger_text)
        f.write("\n\n" + "=" * 40 + "\n\n")
        f.write("## [최종 회의록]\n")
        f.write(final_summary)
    print(Fore.GREEN + f"\n회의록이 '{output_file}'에 저장되었습니다.")


if __name__ == "__main__":
    main()
