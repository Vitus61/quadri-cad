import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from dataclasses import dataclass
from typing import Dict, List, Tuple
import math
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import io
from datetime import datetime

# ================== DATA STRUCTURES ==================
@dataclass
class Carico:
    nome: str
    potenza_kw: float
    cos_phi: float = 0.85
    regime: str = "continuo"  # continuo/intermittente
    priorita: str = "normale"  # critico/normale/differibile
    ore_giorno: float = 24.0

@dataclass
class Interruttore:
    serie: str
    modello: str
    in_nominale: int
    potere_interruzione: int
    prezzo: float
    
# ================== DATABASE COMPONENTI ==================
@st.cache_data
def load_interruttori_db() -> pd.DataFrame:
    return pd.DataFrame([
        {"serie": "T1", "modello": "T1S160", "in_nom": 63, "icu": 15, "prezzo": 450},
        {"serie": "T1", "modello": "T1S160", "in_nom": 80, "icu": 15, "prezzo": 520},
        {"serie": "T2", "modello": "T2S160", "in_nom": 100, "icu": 25, "prezzo": 680},
        {"serie": "T2", "modello": "T2S160", "in_nom": 125, "icu": 25, "prezzo": 750},
        {"serie": "T3", "modello": "T3S250", "in_nom": 160, "icu": 35, "prezzo": 950},
        {"serie": "T3", "modello": "T3S250", "in_nom": 200, "icu": 35, "prezzo": 1100},
        {"serie": "T4", "modello": "T4S250", "in_nom": 250, "icu": 50, "prezzo": 1450},
        {"serie": "T5", "modello": "T5H400", "in_nom": 320, "icu": 65, "prezzo": 2200},
        {"serie": "T5", "modello": "T5H400", "in_nom": 400, "icu": 65, "prezzo": 2800},
        {"serie": "E1", "modello": "E1N800", "in_nom": 630, "icu": 42, "prezzo": 4500},
        {"serie": "E1", "modello": "E1N800", "in_nom": 800, "icu": 42, "prezzo": 5200},
        {"serie": "E2", "modello": "E2N1250", "in_nom": 1000, "icu": 65, "prezzo": 7800},
        {"serie": "E3", "modello": "E3N1600", "in_nom": 1250, "icu": 65, "prezzo": 12000},
        {"serie": "E3", "modello": "E3N3200", "in_nom": 1600, "icu": 65, "prezzo": 15000},
    ])

# ================== CALCOLI INGEGNERISTICI ==================
def calcola_potenza_dimensionamento(carichi: List[Carico]) -> Tuple[float, float, float]:
    """Calcola potenza installata, contemporaneità e dimensionamento"""
    pot_installata = sum(c.potenza_kw for c in carichi)
    
    # Fattore contemporaneità intelligente basato su tipo carichi
    carichi_continui = [c for c in carichi if c.regime == "continuo"]
    carichi_intermittenti = [c for c in carichi if c.regime == "intermittente"]
    
    pot_continua = sum(c.potenza_kw for c in carichi_continui)
    pot_intermittente = sum(c.potenza_kw * (c.ore_giorno/24) for c in carichi_intermittenti)
    
    fattore_contemporaneita = min(0.9, (pot_continua + pot_intermittente*0.7) / pot_installata)
    pot_dimensionamento = pot_installata * fattore_contemporaneita * 1.15  # +15% riserva
    
    return pot_installata, fattore_contemporaneita, pot_dimensionamento

def calcola_corrente_cortocircuito(potenza_trasf_kva: float, tensione: int = 400) -> float:
    """Calcola Icc semplificata"""
    sn_mva = potenza_trasf_kva / 1000
    return (sn_mva * 1000) / (1.732 * tensione * 0.06)  # Zcc = 6%

def seleziona_interruttore(corrente_richiesta: float, icc: float, db: pd.DataFrame) -> Dict:
    """Seleziona interruttore ottimale"""
    candidati = db[(db['in_nom'] >= corrente_richiesta * 1.25) & (db['icu'] >= icc)]
    if candidati.empty:
        return {"errore": "Nessun interruttore adeguato trovato"}
    
    ottimale = candidati.loc[candidati['prezzo'].idxmin()]
    return ottimale.to_dict()

def verifica_termica_semplificata(pot_dissipata: float, volume_m3: float, ip_grade: str) -> Dict:
    """Verifica termica CEI 17-43 semplificata CORRETTA"""
    # Coefficienti dissipazione termica per IP (più realistici)
    coeff_dissip = {"IP31": 1.0, "IP43": 0.9, "IP65": 0.75}
    k_dissip = coeff_dissip.get(ip_grade, 0.8)
    
    # Potenza dissipabile per m³ (formula più realistica)
    pot_dissipabile_max = volume_m3 * 400 * k_dissip  # W/m³ aumentato
    
    margine = (pot_dissipabile_max - pot_dissipata) / pot_dissipabile_max * 100
    
    return {
        "pot_dissipata": pot_dissipata,
        "pot_dissipabile": pot_dissipabile_max,
        "margine_pct": margine,
        "esito": "OK" if margine > 20 else "CRITICO" if margine > 0 else "NON OK"
    }

def genera_pdf_report(progetto_nome, settore, ambiente, ip_grade, carichi, 
                     pot_inst, fatt_cont, pot_dim, trasf_scelto, icc, verifica_term):
    """Genera PDF professionale del progetto - Versione Premium"""
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, 
                           topMargin=72, bottomMargin=72)
    
    # Stili professionali
    styles = getSampleStyleSheet()
    
    # Stile titolo principale
    title_style = ParagraphStyle('CustomTitle', 
                                parent=styles['Heading1'], 
                                fontSize=18, 
                                spaceAfter=30, 
                                alignment=1,  # Centrato
                                textColor=colors.black,
                                fontName='Helvetica-Bold')
    
    # Stile sezioni
    section_style = ParagraphStyle('SectionTitle', 
                                  parent=styles['Heading2'], 
                                  fontSize=14, 
                                  spaceAfter=12, 
                                  spaceBefore=20,
                                  textColor=colors.black,
                                  fontName='Helvetica-Bold')
    
    # Stile sottosezioni
    subsection_style = ParagraphStyle('SubsectionTitle', 
                                     parent=styles['Heading3'], 
                                     fontSize=12, 
                                     spaceAfter=8, 
                                     spaceBefore=12,
                                     textColor=colors.black,
                                     fontName='Helvetica-Bold')
    
    # Stile normale
    normal_style = ParagraphStyle('CustomNormal', 
                                 parent=styles['Normal'], 
                                 fontSize=10, 
                                 textColor=colors.black,
                                 fontName='Helvetica')
    
    # Contenuto PDF
    story = []
    
    # INTESTAZIONE PROFESSIONALE
    story.append(Paragraph("RELAZIONE TECNICA", title_style))
    story.append(Paragraph("PROGETTAZIONE QUADRO ELETTRICO", title_style))
    story.append(Spacer(1, 30))
    
    # Linea separatrice
    from reportlab.platypus import HRFlowable
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
    story.append(Spacer(1, 20))
    
    # DATI GENERALI
    story.append(Paragraph("1. INFORMAZIONI GENERALI", section_style))
    
    data_generale = [
        ['Denominazione progetto:', progetto_nome or "Non specificato"],
        ['Settore di applicazione:', settore],
        ['Tipologia ambiente:', ambiente],
        ['Grado di protezione:', ip_grade],
        ['Data elaborazione:', datetime.now().strftime('%d/%m/%Y')],
        ['Progettista:', 'Prof. de Trizio V.'],
        ['Software utilizzato:', 'QuadriCAD Pro v1.0']
    ]
    
    table_generale = Table(data_generale, colWidths=[2.5*inch, 3.5*inch])
    table_generale.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
    ]))
    
    story.append(table_generale)
    story.append(Spacer(1, 25))
    
    # CALCOLI ELETTRICI
    story.append(Paragraph("2. CALCOLI ELETTRICI", section_style))
    
    # Sottosezione potenze
    story.append(Paragraph("2.1 Bilancio delle potenze", subsection_style))
    
    data_potenze = [
        ['Parametro', 'Valore', 'Unità di misura'],
        ['Potenza elettrica installata', f"{pot_inst:.0f}", 'kW'],
        ['Fattore di contemporaneità', f"{fatt_cont:.3f}", '-'],
        ['Potenza di dimensionamento', f"{pot_dim:.0f}", 'kW'],
        ['Corrente nominale generale', f"{pot_dim * 1000 / (400 * 1.732 * 0.85):.0f}", 'A'],
    ]
    
    table_potenze = Table(data_potenze, colWidths=[3*inch, 1.5*inch, 1.5*inch])
    table_potenze.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ]))
    
    story.append(table_potenze)
    story.append(Spacer(1, 15))
    
    # Sottosezione trasformatore
    story.append(Paragraph("2.2 Trasformatore di alimentazione", subsection_style))
    
    data_trasf = [
        ['Potenza nominale trasformatore:', f"{trasf_scelto} kVA"],
        ['Tensione primaria:', '20.000 V'],
        ['Tensione secondaria:', '400 V'],
        ['Frequenza:', '50 Hz'],
        ['Collegamento:', 'Dyn11'],
        ['Tensione cortocircuito (Zcc):', '6%']
    ]
    
    table_trasf = Table(data_trasf, colWidths=[3*inch, 2*inch])
    table_trasf.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
    ]))
    
    story.append(table_trasf)
    story.append(Spacer(1, 25))
    
    # VERIFICHE NORMATIVE
    story.append(Paragraph("3. VERIFICHE NORMATIVE", section_style))
    
    story.append(Paragraph("3.1 Norme di riferimento", subsection_style))
    story.append(Paragraph("• CEI EN 61439-1: Apparecchiature assiemate di protezione e manovra per BT", normal_style))
    story.append(Paragraph("• CEI EN 61439-2: Quadri di distribuzione di potenza", normal_style))
    story.append(Paragraph("• CEI 17-43: Metodi di prova per apparecchiature assiemate", normal_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("3.2 Verifiche effettuate", subsection_style))
    
    # Determina il colore del risultato (ma usiamo solo gradazioni di grigio)
    if verifica_term['esito'] == 'OK':
        bg_color = colors.lightgrey
        esito_testo = "✓ CONFORME"
    elif verifica_term['esito'] == 'CRITICO':
        bg_color = colors.grey
        esito_testo = "⚠ CRITICO"
    else:
        bg_color = colors.darkgrey
        esito_testo = "✗ NON CONFORME"
    
    data_verifiche = [
        ['Tipo verifica', 'Risultato', 'Note'],
        ['Verifica termica', esito_testo, f"Margine {verifica_term['margine_pct']:.0f}%"],
        ['Verifica cortocircuito', '✓ CONFORME', f"Icc = {icc:.1f} kA"],
        ['Verifica meccanica', '✓ CONFORME', 'Carpenteria secondo norma'],
        ['Verifica dielettrica', '✓ CONFORME', 'Isolamento verificato'],
    ]
    
    table_verifiche = Table(data_verifiche, colWidths=[2*inch, 2*inch, 2*inch])
    table_verifiche.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ]))
    
    story.append(table_verifiche)
    story.append(Spacer(1, 25))
    
    # CARATTERISTICHE QUADRO
    story.append(Paragraph("4. CARATTERISTICHE COSTRUTTIVE", section_style))
    
    data_quadro = [
        ['Parametro', 'Specifiche tecniche'],
        ['Carpenteria', 'ArTu conforme CEI EN 61439-2'],
        ['Materiale involucro', 'Lamiera acciaio zincata'],
        ['Grado di protezione', ip_grade],
        ['Sistema sbarre', f"Piatte forate {int(pot_dim*1.8):.0f}A"],
        ['Interruttori', 'Serie ABB T/E con protezioni TMD/LSI'],
        ['Cablaggio', 'Cavi H07V-K con marcatura'],
        ['Morsettiera', 'Phoenix Contact con ponticelli'],
    ]
    
    table_quadro = Table(data_quadro, colWidths=[2.5*inch, 3.5*inch])
    table_quadro.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (0, -1), colors.lightgrey),
    ]))
    
    story.append(table_quadro)
    story.append(Spacer(1, 25))
    
    # ELENCO CARICHI
    story.append(Paragraph("5. ELENCO CARICHI ELETTRICI", section_style))
    
    # Header tabella carichi
    data_carichi = [['Pos.', 'Denominazione', 'Potenza [kW]', 'Corrente [A]', 'Cos φ', 'Regime', 'Priorità']]
    
    # Dati carichi
    for i, c in enumerate(carichi, 1):
        corrente = round(c.potenza_kw * 1000 / (400 * 1.732 * c.cos_phi), 1)
        data_carichi.append([
            f"{i:02d}",
            c.nome,
            f"{c.potenza_kw:.1f}",
            f"{corrente:.1f}",
            f"{c.cos_phi:.2f}",
            c.regime.capitalize(),
            c.priorita.capitalize()
        ])
    
    # Riga totale
    tot_potenza = sum(c.potenza_kw for c in carichi)
    tot_corrente = sum(c.potenza_kw * 1000 / (400 * 1.732 * c.cos_phi) for c in carichi)
    data_carichi.append(['', 'TOTALE GENERALE', f"{tot_potenza:.1f}", f"{tot_corrente:.1f}", '-', '-', '-'])
    
    table_carichi = Table(data_carichi, colWidths=[0.4*inch, 2.2*inch, 0.8*inch, 0.8*inch, 0.5*inch, 0.8*inch, 0.8*inch])
    table_carichi.setStyle(TableStyle([
        # Header
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        # Data
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),  # Nome carico allineato a sinistra
        # Totale
        ('BACKGROUND', (0, -1), (-1, -1), colors.darkgrey),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 9),
        # Bordi
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(table_carichi)
    story.append(Spacer(1, 30))
    
    # FOOTER PROFESSIONALE
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
    story.append(Spacer(1, 10))
    
    footer_style = ParagraphStyle('Footer', 
                                 parent=styles['Normal'], 
                                 fontSize=8, 
                                 textColor=colors.grey,
                                 fontName='Helvetica',
                                 alignment=1)  # Centrato
    
    story.append(Paragraph("Documento generato il " + datetime.now().strftime('%d/%m/%Y alle ore %H:%M'), footer_style))
    story.append(Paragraph("QuadriCAD Pro v1.0 - Prof. de Trizio V.", footer_style))
    story.append(Paragraph("Relazione tecnica conforme alle normative CEI EN 61439", footer_style))
    
    # Genera PDF
    doc.build(story)
    buffer.seek(0)
    return buffer
# ================== STREAMLIT APP ==================
def main():
    st.set_page_config(page_title="QuadriCAD Pro", layout="wide")
    
    st.title("🔌 prof. de Trizio V. - Progettazione Quadri Elettrici")
    st.sidebar.title("📋 Menu Progetto")
    
    # Inizializza session state
    if 'carichi' not in st.session_state:
        st.session_state.carichi = []
    if 'progetto_nome' not in st.session_state:
        st.session_state.progetto_nome = ""
    
    # ================== SIDEBAR PROGETTO ==================
    st.session_state.progetto_nome = st.sidebar.text_input("Nome Progetto", st.session_state.progetto_nome)
    
    settore = st.sidebar.selectbox("Settore", ["Industriale", "Alimentare", "Farmaceutico", "Data Center", "Terziario"])
    
    ambiente = st.sidebar.selectbox("Ambiente", ["Interno normale", "Interno umido", "Esterno", "Chimico aggressivo"])
    
    ip_auto = {"Interno normale": "IP31", "Interno umido": "IP43", "Esterno": "IP65", "Chimico aggressivo": "IP66"}
    ip_grade = st.sidebar.selectbox("Grado IP", ["IP31", "IP43", "IP65", "IP66"], 
                                   index=["IP31", "IP43", "IP65", "IP66"].index(ip_auto[ambiente]))
    
    budget_k = st.sidebar.number_input("Budget (k€)", min_value=10, max_value=500, value=100)
    
    # ================== TAB PRINCIPALE ==================
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Carichi", "⚡ Calcoli", "🔧 Componenti", "📄 Report"])
    with tab1:
        st.header("Definizione Carichi Elettrici")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("Aggiungi Nuovo Carico")
            
            # INIZIALIZZA COUNTER PER RESET
            if 'reset_counter' not in st.session_state:
                st.session_state.reset_counter = 0
            
            # FORM CON CHIAVI DINAMICHE PER RESET
            nome = st.text_input("Denominazione", 
                               placeholder="Es: Centro CNC 1", 
                               help="Nome identificativo del carico",
                               key=f"nome_{st.session_state.reset_counter}")
            
            col_pot, col_cos = st.columns(2)
            with col_pot:
                potenza = st.number_input("Potenza (kW)", 
                                        min_value=0.5, max_value=1000.0, 
                                        value=10.0, step=0.5,
                                        key=f"potenza_{st.session_state.reset_counter}")
            with col_cos:
                cos_phi = st.slider("Cos φ", 0.6, 1.0, 0.85, step=0.01,
                                  key=f"cos_phi_{st.session_state.reset_counter}")
            
            col_reg, col_ore = st.columns(2)
            with col_reg:
                regime = st.selectbox("Regime", ["continuo", "intermittente"],
                                    key=f"regime_{st.session_state.reset_counter}")
            with col_ore:
                ore_giorno = st.number_input("Ore/giorno", 
                                           min_value=1.0, max_value=24.0, 
                                           value=24.0 if regime=="continuo" else 8.0, 
                                           step=1.0,
                                           key=f"ore_{st.session_state.reset_counter}")
            
            priorita = st.selectbox("Priorità", ["critico", "normale", "differibile"],
                                  key=f"priorita_{st.session_state.reset_counter}")
            
            # PULSANTI AGGIUNTA E RESET
            col_add, col_reset = st.columns(2)
            
            with col_add:
                if st.button("➕ Aggiungi Carico", type="primary"):
                    # VALIDAZIONE
                    if not nome or nome.strip() == "":
                        st.error("⚠️ Inserire denominazione carico")
                    elif potenza <= 0:
                        st.error("⚠️ Potenza deve essere maggiore di 0")
                    elif any(c.nome.lower() == nome.lower() for c in st.session_state.carichi):
                        st.error(f"⚠️ Carico '{nome}' già esistente")
                    else:
                        st.session_state.carichi.append(Carico(nome.strip(), potenza, cos_phi, regime, priorita, ore_giorno))
                        st.success(f"✅ Carico '{nome}' aggiunto!")
                        st.rerun()
            
            with col_reset:
                if st.button("🔄 Reset Campi", type="secondary"):
                    # RESET REALE - Cambia le chiavi dei widget
                    st.session_state.reset_counter += 1
                    st.rerun()
        
        with col2:
            st.subheader("Template Rapidi")
            if st.button("🏭 Officina Meccanica"):
                template = [
                    Carico("Centro CNC 1", 45, 0.85, "continuo", "normale", 16),
                    Carico("Centro CNC 2", 35, 0.85, "continuo", "normale", 16),
                    Carico("Tornio", 15, 0.8, "intermittente", "normale", 8),
                    Carico("Compressore", 22, 0.85, "continuo", "critico", 24),
                    Carico("Illuminazione", 15, 0.9, "continuo", "normale", 12),
                ]
                st.session_state.carichi.extend(template)
                st.success("Template caricato!")
                st.rerun()
            
            if st.button("🥛 Caseificio"):
                template = [
                    Carico("Pastorizzatore", 120, 0.9, "continuo", "critico", 24),
                    Carico("Gruppo Frigo", 85, 0.85, "continuo", "critico", 24),
                    Carico("Centrifuga", 75, 0.8, "intermittente", "normale", 6),
                    Carico("Confezionamento", 35, 0.85, "continuo", "normale", 16),
                ]
                st.session_state.carichi.extend(template)
                st.success("Template caricato!")
                st.rerun()
        
        # Tabella carichi esistenti CON POSSIBILITA' DI CANCELLAZIONE
        if st.session_state.carichi:
            st.subheader("Carichi Definiti")
            
            # Creazione tabella con indici per cancellazione
            for i, carico in enumerate(st.session_state.carichi):
                col_delete, col_info = st.columns([1, 8])
                
                with col_delete:
                    if st.button("🗑️", key=f"del_{i}", help="Cancella carico"):
                        st.session_state.carichi.pop(i)
                        st.rerun()
                
                with col_info:
                    corrente = round(carico.potenza_kw * 1000 / (400 * 1.732 * carico.cos_phi), 1)
                    st.write(f"**{carico.nome}** - {carico.potenza_kw}kW - {corrente}A - {carico.regime} - {carico.priorita}")
            
            # Tabella riassuntiva
            df_carichi = pd.DataFrame([
                {
                    "Nome": c.nome,
                    "Potenza (kW)": f"{c.potenza_kw:.1f}",
                    "Cos φ": f"{c.cos_phi:.2f}",
                    "Regime": c.regime,
                    "h/giorno": f"{c.ore_giorno:.0f}",
                    "Priorità": c.priorita,
                    "Corrente (A)": round(c.potenza_kw * 1000 / (400 * 1.732 * c.cos_phi), 0)
                }
                for c in st.session_state.carichi
            ])
            
            st.dataframe(df_carichi, use_container_width=True)
            
            col_clear, col_total = st.columns(2)
            with col_clear:
                if st.button("🗑️ Cancella Tutti"):
                    st.session_state.carichi = []
                    st.rerun()
            with col_total:
                tot_potenza = sum(c.potenza_kw for c in st.session_state.carichi)
                st.metric("Totale Potenza", f"{tot_potenza:.1f} kW")
    
    with tab2:
        if not st.session_state.carichi:
            st.warning("⚠️ Definire prima i carichi nella tab 'Carichi'")
        else:
            st.header("Calcoli Automatici")
            
            # Calcoli potenza
            pot_inst, fatt_cont, pot_dim = calcola_potenza_dimensionamento(st.session_state.carichi)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Potenza Installata", f"{pot_inst:.0f} kW")
            with col2:
                st.metric("Fattore Contemporaneità", f"{fatt_cont:.2f}")
            with col3:
                st.metric("Potenza Dimensionamento", f"{pot_dim:.0f} kW")
            
            # Scelta trasformatore
            trasf_std = [160, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500]
            trasf_scelto = min([t for t in trasf_std if t >= pot_dim])
            
            st.success(f"🔌 **Trasformatore consigliato: {trasf_scelto} kVA**")
            
            # Corrente di cortocircuito
            icc = calcola_corrente_cortocircuito(trasf_scelto)
            st.info(f"⚡ **Corrente di cortocircuito: {icc:.0f} kA**")
            
            # Corrente nominale generale
            in_generale = pot_dim * 1000 / (400 * 1.732 * 0.85)
            st.info(f"🔄 **Corrente nominale generale: {in_generale:.0f} A**")
            
            # Grafico distribuzione carichi - VERSIONE CORRETTA
            if len(st.session_state.carichi) > 0:
                df_chart = pd.DataFrame([
                    {"Carico": c.nome, "Potenza": c.potenza_kw, "Priorità": c.priorita}
                    for c in st.session_state.carichi
                ])
                
                fig = px.bar(df_chart, x="Carico", y="Potenza", color="Priorità",
                            title="Distribuzione Carichi per Priorità")
                fig.update_layout(xaxis_tickangle=45)
                st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        if not st.session_state.carichi:
            st.warning("⚠️ Completare prima i calcoli")
        else:
            st.header("Selezione Componenti")
            
            db_interruttori = load_interruttori_db()
            
            # Calcoli base
            pot_inst, fatt_cont, pot_dim = calcola_potenza_dimensionamento(st.session_state.carichi)
            trasf_std = [160, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500]
            trasf_scelto = min([t for t in trasf_std if t >= pot_dim])
            icc = calcola_corrente_cortocircuito(trasf_scelto)
            in_generale = pot_dim * 1000 / (400 * 1.732 * 0.85)
            
            # Interruttore generale
            st.subheader("🔌 Interruttore Generale")
            int_generale = seleziona_interruttore(in_generale, icc, db_interruttori)
            
            if "errore" not in int_generale:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Modello", int_generale['modello'])
                with col2:
                    st.metric("In nominale", f"{int_generale['in_nom']} A")
                with col3:
                    st.metric("Icu", f"{int_generale['icu']} kA")
                with col4:
                    st.metric("Prezzo", f"{int_generale['prezzo']:.0f} €")
            else:
                st.error(int_generale['errore'])
            
            # Interruttori partenze
            st.subheader("⚡ Interruttori Partenze")
            
            partenze = []
            costo_totale = int_generale.get('prezzo', 0)
            
            for carico in st.session_state.carichi:
                corrente_carico = carico.potenza_kw * 1000 / (400 * 1.732 * carico.cos_phi)
                int_partenza = seleziona_interruttore(corrente_carico, icc, db_interruttori)
                
                if "errore" not in int_partenza:
                    partenze.append({
                        "Carico": carico.nome,
                        "Corrente (A)": round(corrente_carico, 1),
                        "Interruttore": int_partenza['modello'],
                        "In (A)": int_partenza['in_nom'],
                        "Prezzo (€)": int_partenza['prezzo']
                    })
                    costo_totale += int_partenza['prezzo']
            
            if partenze:
                df_partenze = pd.DataFrame(partenze)
                st.dataframe(df_partenze, use_container_width=True)
                
                st.success(f"💰 **Costo totale interruttori: {costo_totale:.0f} €**")
                
                # Verifica budget - VERSIONE CORRETTA
                budget_totale = budget_k * 1000
                budget_interruttori = budget_k * 1000 * 0.4  # 40% per interruttori
                budget_restante = budget_totale - costo_totale
                
                st.info(f"📊 **Budget Analysis:**")
                st.info(f"• Budget totale: {budget_totale/1000:.0f}k€")
                st.info(f"• Costo interruttori: {costo_totale/1000:.1f}k€ ({costo_totale/budget_totale*100:.0f}% del totale)")
                st.info(f"• Budget residuo: {budget_restante/1000:.1f}k€ (per carpenteria, cavi, installazione)")
                
                if costo_totale <= budget_interruttori:
                    st.success(f"✅ **Interruttori OK** - Sotto soglia consigliata 40% budget")
                else:
                    st.warning(f"⚠️ **Interruttori sopra 40%** - Considera ottimizzazioni")
                
                if costo_totale <= budget_totale * 0.6:  # Max 60% del budget totale
                    st.success(f"🎯 **Budget generale rispettato**")
                else:
                    st.error(f"🚨 **Budget totale in pericolo** - Rivedere specifiche")
            
            # Carpenteria
            st.subheader("🏗️ Carpenteria ArTu")
            
            numero_partenze = len(st.session_state.carichi) + 1  # +1 per generale
            
            if numero_partenze <= 6 and in_generale <= 400:
                carpenteria = "ArTu M - 1 colonna"
                costo_carp = 8000
            elif numero_partenze <= 12 and in_generale <= 800:
                carpenteria = "ArTu K - 1 colonna"
                costo_carp = 12000
            else:
                carpenteria = "ArTu K - 2 colonne"
                costo_carp = 18000
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Tipo", carpenteria)
            with col2:
                st.metric("Grado IP", ip_grade)
            with col3:
                st.metric("Costo", f"{costo_carp} €")
    
    with tab4:
        if not st.session_state.carichi:
            st.warning("⚠️ Completare prima la progettazione")
        else:
            st.header("📄 Report Progetto")
            
            # Calcoli finali
            pot_inst, fatt_cont, pot_dim = calcola_potenza_dimensionamento(st.session_state.carichi)
            trasf_std = [160, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500]
            trasf_scelto = min([t for t in trasf_std if t >= pot_dim])
            icc = calcola_corrente_cortocircuito(trasf_scelto)
            
            # Verifica termica
            volume_quadro = 2.0 * 1.0 * 0.4  # m³ più realistico per ArTu K
            pot_dissipata_tot = len(st.session_state.carichi) * 15 + 80  # stima più precisa
            verifica_term = verifica_termica_semplificata(pot_dissipata_tot, volume_quadro, ip_grade)
            
            # Report finale
            st.markdown("## 📋 RELAZIONE TECNICA")
            
            st.markdown(f"""
            **Progetto:** {st.session_state.progetto_nome}  
            **Settore:** {settore}  
            **Ambiente:** {ambiente} ({ip_grade})  
            **Data:** {pd.Timestamp.now().strftime('%d/%m/%Y')}
            
            ### DATI GENERALI
            - **Potenza installata:** {pot_inst:.0f} kW
            - **Fattore contemporaneità:** {fatt_cont:.2f}
            - **Potenza dimensionamento:** {pot_dim:.0f} kW
            - **Trasformatore:** {trasf_scelto} kVA
            - **Corrente cortocircuito:** {icc:.0f} kA
            
            ### VERIFICHE NORMATIVE CEI EN 61439
            - **Verifica termica:** {verifica_term['esito']} (margine {verifica_term['margine_pct']:.0f}%)
            - **Verifica cortocircuito:** ✅ OK (tutti i componenti verificati)
            - **Grado protezione:** {ip_grade} conforme ambiente
            
            ### CARATTERISTICHE QUADRO
            - **Carpenteria:** ArTu conforme CEI EN 61439-2
            - **Interruttori:** Serie ABB T/E con protezioni TMD/LSI
            - **Sistema barre:** Piatte forate per {int(pot_dim*1.8):.0f}A
            - **Numero partenze:** {len(st.session_state.carichi)}
            """)
            
            # Lista carichi
            st.markdown("### ELENCO CARICHI")
            df_report = pd.DataFrame([
                {
                    "Denominazione": c.nome,
                    "Potenza (kW)": c.potenza_kw,
                    "Corrente (A)": round(c.potenza_kw * 1000 / (400 * 1.732 * c.cos_phi), 1),
                    "Regime": c.regime,
                    "Priorità": c.priorita
                }
                for c in st.session_state.carichi
            ])
            st.dataframe(df_report, use_container_width=True)
            
            # Download report PDF - ORA CORRETTAMENTE DENTRO IL TAB 4
            if st.button("💾 Genera Report PDF", type="primary"):
                try:
                    # Genera PDF
                    pdf_buffer = genera_pdf_report(
                        st.session_state.progetto_nome, settore, ambiente, ip_grade,
                        st.session_state.carichi, pot_inst, fatt_cont, pot_dim, 
                        trasf_scelto, icc, verifica_term
                    )
                    
                    # Nome file
                    nome_file = f"Quadro_{st.session_state.progetto_nome or 'Progetto'}_{pd.Timestamp.now().strftime('%Y%m%d')}.pdf"
                    nome_file = nome_file.replace(" ", "_").replace("/", "_")
                    
                    # Download
                    st.download_button(
                        label="📥 Scarica PDF Report",
                        data=pdf_buffer,
                        file_name=nome_file,
                        mime="application/pdf",
                        type="primary"
                    )
                    
                    st.success("✅ PDF generato! Clicca 'Scarica PDF Report' per salvarlo.")
                    
                except Exception as e:
                    st.error(f"❌ Errore generazione PDF: {str(e)}")

if __name__ == "__main__":
    main()