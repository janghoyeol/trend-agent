"""하루 Claude 비용 상한 (ADR 0005). 설명 1건을 시작하기 전에 최악 비용만큼 예약하고, 끝나면 실제 비용으로 정산한다."""
import threading
from datetime import date

# 설명 1건 최악 비용 추정 (검색 5회, 호출 6회, 캐시 미적중 가정). 실측 후 조정.
WORST_CASE_USD = {"claude-haiku-5-5": 0.01, "claude-sonnet-5-5": 0.15}


class DailyBudget:
    """프로세스 메모리에만 있다 → 재시작하면 0부터. 최종 안전장치는 Anthropic 콘솔 사용 한도."""

    def __init__(self, cap_usd: float, today=date.today):
        self.cap = cap_usd
        self._today = today
        self._day = None
        self.spent = 0.0
        self.reserved = 0.0
        self._lock = threading.Lock()

    def _roll(self):
        if self._day != self._today():
            self._day, self.spent, self.reserved = self._today(), 0.0, 0.0

    def reserve(self, model: str) -> float | None:
        """예약 성공 시 예약액, 한도 초과면 None."""
        amount = WORST_CASE_USD.get(model, 0.15)
        with self._lock:
            self._roll()
            if self.spent + self.reserved + amount > self.cap:
                return None
            self.reserved += amount
            return amount

    def settle(self, reserved: float, actual: float) -> None:
        with self._lock:
            self._roll()
            self.reserved = max(0.0, self.reserved - reserved)
            self.spent += actual

    @property
    def remaining(self) -> float:
        with self._lock:
            self._roll()
            return max(0.0, self.cap - self.spent - self.reserved)
