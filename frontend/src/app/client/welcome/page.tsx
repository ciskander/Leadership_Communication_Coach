'use client';

import { useRouter } from 'next/navigation';
import { dismissWelcome } from '@/lib/onboarding';
import { STRINGS } from '@/config/strings';

const S = STRINGS.onboarding;

const steps = [
  { num: 1, icon: '📚', title: S.journeyStep1Title, desc: S.journeyStep1Desc },
  { num: 2, icon: '✨', title: S.journeyStep2Title, desc: S.journeyStep2Desc },
  { num: 3, icon: '🧪', title: S.journeyStep3Title, desc: S.journeyStep3Desc },
  { num: 4, icon: '📈', title: S.journeyStep4Title, desc: S.journeyStep4Desc },
];

const expectations = [S.expectItem1, S.expectItem2, S.expectItem3];

export default function WelcomePage() {
  const router = useRouter();

  function handleGetStarted() {
    dismissWelcome();
    router.push('/client');
  }

  function handleSkip() {
    dismissWelcome();
    router.push('/client');
  }

  return (
    <div className="max-w-2xl mx-auto py-8 space-y-10">
      {/* Skip link */}
      <div className="flex justify-end">
        <button
          onClick={handleSkip}
          className="text-xs text-stone-400 hover:text-stone-600 transition-colors"
        >
          {S.skip}
        </button>
      </div>

      {/* Hero */}
      <div className="text-center space-y-3">
        <h1 className="text-3xl font-bold text-stone-900">{S.welcomeHeading}</h1>
        <p className="text-stone-500 text-base">{S.welcomeSubheading}</p>
        <p className="text-sm text-stone-500 leading-relaxed max-w-lg mx-auto">
          {S.welcomeIntro}
        </p>
      </div>

      {/* How it works — 4-step journey */}
      <section className="space-y-4">
        <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
          {S.journeyHeading}
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {steps.map((step) => (
            <div
              key={step.num}
              className="bg-white rounded-2xl border border-stone-200 p-5 space-y-2"
            >
              <div className="flex items-center gap-2">
                <span className="w-7 h-7 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center text-xs font-bold">
                  {step.num}
                </span>
                <span className="text-base">{step.icon}</span>
                <h3 className="text-sm font-semibold text-stone-800">{step.title}</h3>
              </div>
              <p className="text-xs text-stone-500 leading-relaxed">{step.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* What to expect */}
      <section className="space-y-3">
        <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
          {S.expectHeading}
        </h2>
        <div className="bg-white rounded-2xl border border-stone-200 p-5">
          <ul className="space-y-2">
            {expectations.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-stone-600">
                <span className="text-emerald-500 mt-0.5">•</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* CTA */}
      <div className="flex justify-center">
        <button
          onClick={handleGetStarted}
          className="px-8 py-3 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 transition-colors shadow-sm"
        >
          {S.getStarted}
        </button>
      </div>
    </div>
  );
}
