import os
import json
import time
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ============================================================
# CONFIG — via variables d'environnement Railway
# ============================================================
PLANITY_EMAIL = os.environ.get("PLANITY_EMAIL")
PLANITY_PASSWORD = os.environ.get("PLANITY_PASSWORD")
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL")

def init_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    driver = webdriver.Chrome(options=options)
    return driver

def login_planity(driver):
    print("Connexion à Planity...")
    driver.get("https://pro.planity.com")
    time.sleep(3)
    
    wait = WebDriverWait(driver, 15)
    
    # Champ email
    email_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[placeholder*='mail']")))
    email_field.clear()
    email_field.send_keys(PLANITY_EMAIL)
    time.sleep(1)
    
    # Champ mot de passe
    password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
    password_field.clear()
    password_field.send_keys(PLANITY_PASSWORD)
    time.sleep(1)
    
    # Bouton connexion
    submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button.login, button.connexion")
    submit_btn.click()
    time.sleep(4)
    
    print("Connecté !")

def get_today_appointments(driver):
    print("Récupération des RDV du jour...")
    rdvs = []
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Naviguer vers l'agenda
    driver.get("https://pro.planity.com/agenda")
    time.sleep(3)
    
    wait = WebDriverWait(driver, 15)
    
    # Trouver tous les RDV visibles (éléments cliquables dans l'agenda)
    rdv_elements = driver.find_elements(By.CSS_SELECTOR, "[class*='appointment'], [class*='rdv'], [class*='event'], [data-appointment]")
    
    print(f"Nombre de RDV trouvés : {len(rdv_elements)}")
    
    for i, rdv_el in enumerate(rdv_elements):
        try:
            # Cliquer sur le RDV
            driver.execute_script("arguments[0].click();", rdv_el)
            time.sleep(1.5)
            
            # Extraire les données du modal
            rdv_data = extract_rdv_data(driver, today)
            if rdv_data:
                rdvs.append(rdv_data)
                print(f"RDV {i+1} extrait : {rdv_data.get('client', 'inconnu')}")
            
            # Fermer le modal
            close_btns = driver.find_elements(By.CSS_SELECTOR, "button.close, [aria-label='Close'], .modal-close, button[class*='close']")
            if close_btns:
                close_btns[0].click()
            else:
                driver.find_element(By.TAG_NAME, "body").send_keys("\x1b")
            time.sleep(1)
            
        except Exception as e:
            print(f"Erreur RDV {i+1}: {e}")
            continue
    
    return rdvs

def extract_rdv_data(driver, today):
    try:
        wait = WebDriverWait(driver, 5)
        
        # Extraire toutes les données visibles dans le modal
        data = {
            "date": today,
            "client": "",
            "sexe": "Autre",
            "code_postal": "",
            "prestation": "",
            "collaboratrice": "",
            "duree_min": 0,
            "prix": 0.0,
            "cabine": "",
            "statut": "Honoré"
        }
        
        # Nom client
        try:
            client_el = driver.find_element(By.CSS_SELECTOR, "[class*='client-name'], [class*='clientName'], h3, .rdv-client")
            data["client"] = client_el.text.strip()
        except:
            pass
        
        # Sexe (boutons radio Femme/Homme/Enfant/Autre)
        try:
            sexe_buttons = driver.find_elements(By.CSS_SELECTOR, "button[class*='gender'], [class*='sexe'] button, .gender-selector button")
            for btn in sexe_buttons:
                if "active" in btn.get_attribute("class") or btn.get_attribute("aria-selected") == "true":
                    data["sexe"] = btn.text.strip()
                    break
        except:
            pass
        
        # Code postal
        try:
            cp_el = driver.find_element(By.CSS_SELECTOR, "input[placeholder*='postal'], input[name*='postal'], [class*='postal']")
            data["code_postal"] = cp_el.get_attribute("value") or cp_el.text.strip()
        except:
            pass
        
        # Prestation
        try:
            presta_el = driver.find_element(By.CSS_SELECTOR, "[class*='prestation'], [class*='service-name'], .appointment-service")
            data["prestation"] = presta_el.text.strip()
        except:
            pass
        
        # Collaboratrice
        try:
            collab_el = driver.find_element(By.CSS_SELECTOR, "[class*='collaborator'], [class*='practitioner'], .staff-name")
            data["collaboratrice"] = collab_el.text.strip()
        except:
            pass
        
        # Durée
        try:
            duree_el = driver.find_element(By.CSS_SELECTOR, "[class*='duration'], [class*='duree']")
            duree_text = duree_el.text.strip()
            # Ex: "50min" ou "1h30"
            if "h" in duree_text:
                parts = duree_text.replace("min", "").split("h")
                h = int(parts[0]) if parts[0] else 0
                m = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                data["duree_min"] = h * 60 + m
            else:
                data["duree_min"] = int(duree_text.replace("min", "").strip())
        except:
            pass
        
        # Prix
        try:
            prix_el = driver.find_element(By.CSS_SELECTOR, "[class*='price'], [class*='prix'], [class*='amount']")
            prix_text = prix_el.text.strip().replace("€", "").replace(",", ".").strip()
            data["prix"] = float(prix_text)
        except:
            pass
        
        # Cabine
        try:
            cabine_el = driver.find_element(By.CSS_SELECTOR, "[class*='room'], [class*='cabine'], [class*='cabin']")
            data["cabine"] = cabine_el.text.strip()
        except:
            pass
        
        # Ne retourner que si on a au moins un client ou une prestation
        if data["client"] or data["prestation"]:
            return data
        return None
        
    except Exception as e:
        print(f"Erreur extraction: {e}")
        return None

def send_to_n8n(rdvs, date):
    print(f"Envoi de {len(rdvs)} RDVs à n8n...")
    
    payload = {
        "date": date,
        "total_rdvs": len(rdvs),
        "ca_total": sum(r.get("prix", 0) for r in rdvs),
        "rdvs": rdvs
    }
    
    response = requests.post(
        N8N_WEBHOOK_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    
    print(f"Réponse n8n: {response.status_code}")
    return response.status_code == 200

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"=== Scraping Planity - {today} ===")
    
    if not all([PLANITY_EMAIL, PLANITY_PASSWORD, N8N_WEBHOOK_URL]):
        print("ERREUR: Variables d'environnement manquantes!")
        print(f"PLANITY_EMAIL: {'OK' if PLANITY_EMAIL else 'MANQUANT'}")
        print(f"PLANITY_PASSWORD: {'OK' if PLANITY_PASSWORD else 'MANQUANT'}")
        print(f"N8N_WEBHOOK_URL: {'OK' if N8N_WEBHOOK_URL else 'MANQUANT'}")
        return
    
    driver = None
    try:
        driver = init_driver()
        login_planity(driver)
        rdvs = get_today_appointments(driver)
        
        if rdvs:
            success = send_to_n8n(rdvs, today)
            if success:
                print(f"✅ {len(rdvs)} RDVs envoyés à n8n avec succès!")
            else:
                print("❌ Erreur envoi n8n")
        else:
            print("Aucun RDV trouvé aujourd'hui")
            # Envoyer quand même un rapport vide
            send_to_n8n([], today)
            
    except Exception as e:
        print(f"ERREUR CRITIQUE: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
