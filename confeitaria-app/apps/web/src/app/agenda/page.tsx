import Link from "next/link";

export default function Agenda() {
  return (
    <main className="min-h-screen">
      <header className="bg-pink-600 text-white p-6 shadow-md">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link href="/" className="text-2xl font-bold">Confeitaria</Link>
          <nav className="flex gap-6 text-sm font-medium">
            <Link href="/" className="hover:text-pink-200">Início</Link>
            <Link href="/catalogo" className="hover:text-pink-200">Catálogo</Link>
            <Link href="/agenda" className="text-pink-200">Agenda</Link>
          </nav>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8">Agenda de Encomendas</h1>

        <div className="bg-white rounded-2xl shadow-sm p-6 mb-8">
          <h2 className="text-xl font-semibold mb-4">Datas Disponíveis</h2>
          <div className="grid grid-cols-7 gap-2 text-center mb-4">
            {["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"].map((d) => (
              <div key={d} className="text-xs font-medium text-stone-500 py-1">{d}</div>
            ))}
            {Array.from({ length: 35 }, (_, i) => (
              <div key={i} className={`py-2 rounded-lg text-sm ${i > 3 && i < 17 ? "bg-pink-100 text-pink-700 cursor-pointer hover:bg-pink-200" : "text-stone-300"}`}>
                {i + 1}
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h2 className="text-xl font-semibold mb-4">Solicitar Agendamento</h2>
          <form className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Nome</label>
              <input type="text" className="w-full border rounded-lg px-3 py-2" placeholder="Seu nome" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Data desejada</label>
              <input type="date" className="w-full border rounded-lg px-3 py-2" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Tipo de bolo</label>
              <select className="w-full border rounded-lg px-3 py-2">
                <option>Bolo de Chocolate</option>
                <option>Bolo de Morango</option>
                <option>Bolo de Cenoura</option>
                <option>Bolo Personalizado</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Observações</label>
              <textarea className="w-full border rounded-lg px-3 py-2" rows={3} placeholder="Descreva o que deseja..." />
            </div>
            <button type="submit" className="bg-pink-600 text-white px-6 py-3 rounded-full font-medium hover:bg-pink-700 transition">
              Solicitar Agendamento
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
