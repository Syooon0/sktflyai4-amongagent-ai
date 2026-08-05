import type { Verdict } from "../types";

interface JudgePanelProps {
  isJudging: boolean;
  verdict: Verdict | null;
}

export default function JudgePanel({ isJudging, verdict }: JudgePanelProps) {
  return (
    <section className="judge-panel" aria-label="판단 에이전트">
      <div className="judge-panel__character" aria-hidden="true">
        🕵️
      </div>
      <div className="judge-panel__bubble" aria-live="polite">
        {isJudging && <p>답변을 분석하고 있어요…</p>}
        {!isJudging && !verdict && <p>모두의 답변을 기다리고 있어요.</p>}
        {verdict && (
          <>
            <p>{verdict.reason}</p>
            <div
              className="judge-panel__confidence"
              role="meter"
              aria-label="판단 확신도"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={verdict.confidence}
            >
              <span
                className="judge-panel__confidence-fill"
                style={{ width: `${verdict.confidence}%` }}
              />
              <span>{verdict.confidence}%</span>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
