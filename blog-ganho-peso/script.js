// Smooth scroll para links internos
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Animação de elementos ao entrar na tela
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Observar cards para animação
document.querySelectorAll('.receita-card, .dica-card, .sobre-card').forEach(card => {
    card.style.opacity = '0';
    card.style.transform = 'translateY(30px)';
    card.style.transition = 'all 0.6s ease';
    observer.observe(card);
});

// Efeito parallax no hero
window.addEventListener('scroll', () => {
    const hero = document.querySelector('.hero');
    const scrolled = window.pageYOffset;
    if (hero) {
        hero.style.backgroundPositionY = scrolled * 0.5 + 'px';
    }
});

// Contador de calorias (exemplo interativo)
function calcularCaloriasDiarias() {
    const peso = prompt('Qual seu peso atual (kg)?');
    const altura = prompt('Qual sua altura (cm)?');
    const idade = prompt('Qual sua idade?');
    
    if (peso && altura && idade) {
        // Fórmula de Harris-Benedict simplificada
        const tmb = 88.362 + (13.397 * parseFloat(peso)) + (4.799 * parseFloat(altura)) - (5.677 * parseInt(idade));
        const caloriasManutencao = tmb * 1.55; // Atividade moderada
        const caloriasGanho = caloriasManutencao + 500; // Superávit calórico
        
        alert(`Para ganhar peso de forma saudável:\n\nCalorias para manter: ${Math.round(caloriasManutencao)} kcal/dia\nCalorias para ganhar: ${Math.round(caloriasGanho)} kcal/dia\n\nadicione 300-500 kcal às suas refeições diárias!`);
    }
}

// Adicionar botão de calculadora (opcional)
document.addEventListener('DOMContentLoaded', () => {
    const btnCalc = document.createElement('button');
    btnCalc.textContent = '🧮 Calcular Minhas Calorias';
    btnCalc.className = 'btn-cta';
    btnCalc.style.marginTop = '20px';
    btnCalc.onclick = calcularCaloriasDiarias;
    
    const hero = document.querySelector('.hero-content');
    if (hero) {
        hero.appendChild(btnCalc);
    }
});

// Mensagem motivacional aleatória
const mensagens = [
    "Você é incrível do jeitinho que é! 💖",
    "Cada dia é uma nova chance de se sentir melhor consigo mesmo! ✨",
    "Seu corpo é seu lar - cuide dele com amor! 🏠",
    "Progresso, não perfeição! 🌱",
    "Você merece se sentir confiante e feliz! 🌟",
    "Coma com prazer, viva com leveza! 🍽️",
    "Suas curvas estão chegando - paciência! ⏳"
];

function mostrarMensagemMotivacional() {
    const msg = mensagens[Math.floor(Math.random() * mensagens.length)];
    const div = document.createElement('div');
    div.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: linear-gradient(135deg, #E91E63, #FF6F00);
        color: white;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        z-index: 1000;
        max-width: 300px;
        animation: slideIn 0.5s ease;
    `;
    div.innerHTML = `
        <p style="margin: 0; font-weight: 500;">${msg}</p>
        <button onclick="this.parentElement.remove()" style="
            background: white;
            color: #E91E63;
            border: none;
            padding: 5px 15px;
            border-radius: 20px;
            margin-top: 10px;
            cursor: pointer;
            font-weight: 600;
        ">Fechar</button>
    `;
    document.body.appendChild(div);
    
    setTimeout(() => {
        if (div.parentElement) {
            div.remove();
        }
    }, 5000);
}

// Mostrar mensagem motivacional após 10 segundos
setTimeout(mostrarMensagemMotivacional, 10000);

// Adicionar animação CSS para slideIn
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateX(100px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
`;
document.head.appendChild(style);
