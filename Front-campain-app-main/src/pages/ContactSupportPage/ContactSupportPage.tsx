export default function ContactSupportPage() {
  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-10 sm:p-16 text-center">
          <div className="inline-flex items-center gap-2 rounded-full bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-700">
            Support
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 mt-6">Contactez-nous</h1>
          <p className="text-gray-600 mt-3 max-w-2xl mx-auto">
            Pour toute question, contactez notre equipe support.
          </p>
          <div className="mt-8 space-y-3">
            <a
              href="mailto:a.ghaouta@neoimpact.ma"
              className="block text-lg font-semibold text-slate-900 hover:text-slate-700"
            >
              a.ghaouta@neoimpact.ma
            </a>
            <a
              href="tel:0696823459"
              className="block text-lg font-semibold text-slate-900 hover:text-slate-700"
            >
              0696823459
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
