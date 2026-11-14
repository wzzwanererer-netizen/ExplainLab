import { useState } from "react";
import { api } from "../../api/client";
import type {
  AnswerFeedback,
  ExperimentCompleteResult,
  ExperimentSession,
  QuizQuestionPublic,
} from "../../api/types";
import { MODE_META, percent, scoreTone } from "../../lib/experiments";

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

const OPTION_LETTER = ["A", "B", "C", "D", "E", "F"];

interface Props {
  session: ExperimentSession;
  onOpenItem: (itemId: string) => void;
  onCompleted: (result: ExperimentCompleteResult) => void;
  onRetry: (session: ExperimentSession) => void;
  onError: (message: string) => void;
}

interface Answered {
  value: number;
  feedback: AnswerFeedback;
}

/** 得分环：SVG 描边进度，颜色 + 文字双重表达掌握程度。 */
function ScoreRing({ score }: { score: number }) {
  const tone = scoreTone(score);
  const r = 52;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative h-36 w-36 shrink-0">
      <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90">
        <circle cx="64" cy="64" r={r} fill="none" stroke="#1e293b" strokeWidth="10" />
        <circle
          cx="64"
          cy="64"
          r={r}
          fill="none"
          stroke={tone.hex}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - Math.max(0, Math.min(1, score)))}
          className="exp-ring"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-3xl font-semibold ${tone.text}`}>{percent(score)}%</span>
        <span className="text-xs text-slate-400">{tone.label}</span>
      </div>
    </div>
  );
}

/** 单题回顾：高亮正确答案，标记作答对错。 */
function ReviewCard({
  question,
  userValue,
}: {
  question: QuizQuestionPublic;
  userValue?: number;
}) {
  const correct = question.correct_index ?? -1;
  const isRight = userValue === correct;
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <div className="mb-2 flex items-start gap-2">
        <span
          className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs ${
            isRight ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300"
          }`}
        >
          {isRight ? "答对" : "答错"}
        </span>
        <p className="text-sm text-slate-200">{question.prompt}</p>
      </div>
      <ul className="space-y-1">
        {question.options.map((opt, i) => (
          <li
            key={i}
            className={`flex items-center gap-2 rounded-md px-2 py-1 text-sm ${
              i === correct
                ? "bg-emerald-500/10 text-emerald-200"
                : i === userValue
                  ? "bg-red-500/10 text-red-200"
                  : "text-slate-400"
            }`}
          >
            <span className="text-xs opacity-70">{OPTION_LETTER[i] ?? i + 1}</span>
            {opt}
            {i === correct && <span className="ml-auto text-xs">正确答案</span>}
            {i === userValue && i !== correct && (
              <span className="ml-auto text-xs">你的选择</span>
            )}
          </li>
        ))}
      </ul>
      {question.explanation && (
        <p className="mt-2 text-xs text-slate-400">解析：{question.explanation}</p>
      )}
    </div>
  );
}

/**
 * 测验 Runner：逐题作答 → 服务端即时判分 → 反馈解析与来源 → 完成得分环 + 回顾。
 * 正确答案服务端持有，作答前不下发；已完成会话 reopened 时进入回顾模式。
 */
export function QuizRunner({ session, onOpenItem, onCompleted, onRetry, onError }: Props) {
  const questions = session.payload.questions ?? [];
  const total = questions.length;
  const accent = MODE_META.quiz.accent;

  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, Answered>>({});
  const [result, setResult] = useState<ExperimentCompleteResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [completing, setCompleting] = useState(false);

  const answeredCount = Object.keys(answers).length;
  const reviewOnly = session.status === "completed" && result === null;

  async function handleAnswer(value: number) {
    if (answers[index] || submitting) return;
    setSubmitting(true);
    try {
      const feedback = await api.answerExperiment(session.id, index, value);
      setAnswers((prev) => ({ ...prev, [index]: { value, feedback } }));
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleComplete() {
    setCompleting(true);
    try {
      const list = Object.entries(answers).map(([idx, a]) => ({
        index: Number(idx),
        value: a.value,
      }));
      const res = await api.completeExperiment(session.id, list);
      setResult(res);
      onCompleted(res);
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setCompleting(false);
    }
  }

  // 完成态：得分环 + 逐题回顾 + 再测一次。
  if (result) {
    const revealed = result.session.payload.questions ?? [];
    const userByIndex = new Map(result.attempt.answers.map((a) => [a.index, a.value]));
    return (
      <div className="exp-fade-in space-y-5">
        <div className="flex flex-wrap items-center gap-6 rounded-xl border border-slate-800 bg-slate-900 p-5">
          <ScoreRing score={result.attempt.score} />
          <div className="space-y-1">
            <h3 className="text-lg font-semibold text-slate-100">测验完成</h3>
            <p className="text-sm text-slate-300">
              答对 {result.attempt.correct_count} / {result.attempt.total} 题
            </p>
            <p className="text-xs text-slate-500">
              判分由服务端完成，正确答案与解析现已揭示。
            </p>
            <button
              type="button"
              onClick={() => onRetry(session)}
              className={`mt-2 rounded-md border px-4 py-1.5 text-sm font-medium ${accent.border} ${accent.text} hover:bg-slate-800`}
            >
              再测一次
            </button>
          </div>
        </div>
        <div className="space-y-3">
          {revealed.map((q) => (
            <ReviewCard key={q.index} question={q} userValue={userByIndex.get(q.index)} />
          ))}
        </div>
      </div>
    );
  }

  // 已完成会话重新打开：仅回顾题目与解析（无个人得分记录）。
  if (reviewOnly) {
    return (
      <div className="exp-fade-in space-y-4">
        <div
          role="status"
          className="rounded-md border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-400"
        >
          本次测验已完成，以下为题目与正确答案回顾。
          <button
            type="button"
            onClick={() => onRetry(session)}
            className={`ml-3 rounded-md border px-3 py-1 text-xs ${accent.border} ${accent.text}`}
          >
            再测一次
          </button>
        </div>
        <div className="space-y-3">
          {questions.map((q) => (
            <ReviewCard key={q.index} question={q} />
          ))}
        </div>
      </div>
    );
  }

  const current = questions[index];
  const answered = answers[index];
  if (!current) {
    return <p className="text-sm text-slate-500">本次测验暂无题目。</p>;
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>
            第 {index + 1} / {total} 题 · 已答 {answeredCount}
          </span>
          <span className={`rounded-full px-2.5 py-0.5 ${accent.badge}`}>
            {current.kind === "true_false" ? "判断题" : "单选题"}
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${total ? (answeredCount / total) * 100 : 0}%`,
              backgroundColor: accent.hex,
            }}
          />
        </div>
      </div>

      <div key={index} className="exp-fade-in rounded-xl border border-slate-800 bg-slate-900 p-5">
        <p className="mb-4 text-base font-medium text-slate-100">{current.prompt}</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {current.options.map((opt, i) => {
            const isCorrect = answered && i === answered.feedback.correct_value;
            const isWrongPick = answered && i === answered.value && !answered.feedback.correct;
            const state = isCorrect
              ? "border-emerald-500 bg-emerald-500/10 text-emerald-200"
              : isWrongPick
                ? "border-red-500 bg-red-500/10 text-red-200"
                : answered
                  ? "border-slate-800 bg-slate-950 text-slate-500"
                  : "border-slate-700 bg-slate-950 text-slate-200 hover:border-slate-500";
            return (
              <button
                key={i}
                type="button"
                disabled={!!answered || submitting}
                onClick={() => void handleAnswer(i)}
                className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors disabled:cursor-default ${state} ${
                  isCorrect || isWrongPick ? "exp-pop" : ""
                }`}
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-current text-xs opacity-80">
                  {OPTION_LETTER[i] ?? i + 1}
                </span>
                {opt}
              </button>
            );
          })}
        </div>

        {answered && (
          <div
            role="status"
            className={`exp-pop mt-4 rounded-lg border p-3 text-sm ${
              answered.feedback.correct
                ? "border-emerald-900 bg-emerald-950/40 text-emerald-200"
                : "border-red-900 bg-red-950/40 text-red-200"
            }`}
          >
            <p className="font-medium">
              {answered.feedback.correct ? "回答正确" : "回答错误"}
            </p>
            {answered.feedback.explanation && (
              <p className="mt-1 text-slate-300">{answered.feedback.explanation}</p>
            )}
            <button
              type="button"
              onClick={() => onOpenItem(current.source_item_id)}
              className="mt-2 rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
            >
              查看来源知识
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={index === 0}
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          className="rounded-md border border-slate-700 px-4 py-1.5 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-40"
        >
          上一题
        </button>
        {index < total - 1 ? (
          <button
            type="button"
            disabled={!answered}
            onClick={() => setIndex((i) => Math.min(total - 1, i + 1))}
            className="rounded-md border border-slate-700 px-4 py-1.5 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-40"
          >
            下一题
          </button>
        ) : null}
        <button
          type="button"
          disabled={answeredCount < total || completing}
          onClick={() => void handleComplete()}
          className={`ml-auto rounded-md px-5 py-1.5 text-sm font-medium text-slate-900 disabled:opacity-40 ${
            answeredCount < total ? "bg-slate-600" : "bg-amber-300 hover:bg-amber-200"
          }`}
        >
          {completing ? "提交中…" : "完成测验"}
        </button>
      </div>
    </div>
  );
}