import os
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

# ============================================================
# CONFIG — via variables d'environnement Railway
# ============================================================
PLANITY_EMAIL = os.environ.get("PLANITY_EMAIL")
PLANITY_PASSWORD = os.environ.get("PLANITY_PASSWORD")
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL")


def login_planity(page):
    print("Connexion à Planity...")
    page.goto("https://pro.planity.com", wait_until="domcontentloaded", timeout=60000)
    print(f"URL: {page.url}")

    # Attendre et cliquer sur le champ email
    email_loc = page.locator("input[type='email'], input[name='email']").first
    email_loc.wait_for(state="visible", timeout=15000)
    email_loc.click()
    # press_sequentially déclenche les événements React onChange
    email_loc.press_sequentially(PLANITY_EMAIL, delay=50)
    print("Email rempli")
    page.wait_for_timeout(1000)

    # Debug : lister tous les inputs présents
    for inp in page.query_selector_all("input"):
        try:
            print(f"  Input: type={inp.get_attribute('type')} name={inp.get_attribute('name')} id={inp.get_attribute('id')} visible={inp.is_visible()}")
        except Exception:
            pass

    if page.is_visible("input[type='password']"):
        print("Password déjà visible — formulaire 1 étape")
    else:
        print("Password caché — soumission de l'email...")
        # Tab déclenche blur → onChange React, puis Enter soumet
        page.keyboard.press("Tab")
        page.wait_for_timeout(2000)
        if not page.is_visible("input[type='password']"):
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)
        # Essayer input[type=submit] et [role=button]
        if not page.is_visible("input[type='password']"):
            for sel in ["input[type='submit']", "[role='button']", "a[class*='button']", "a[class*='btn']"]:
                try:
                    page.click(sel, timeout=2000)
                    page.wait_for_timeout(2000)
                    if page.is_visible("input[type='password']"):
                        print(f"Débloqué via: {sel}")
                        break
                except Exception:
                    pass

    page.wait_for_selector("input[type='password']", state="visible", timeout=15000)
    pwd_loc = page.locator("input[type='password']").first
    pwd_loc.click()
    pwd_loc.press_sequentially(PLANITY_PASSWORD, delay=50)
    print("Mot de passe rempli")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle", timeout=30000)
    print(f"URL finale: {page.url}")
    print("Connecté !")


def get_today_appointments(page):
    print("Récupération des RDV du jour...")
    rdvs = []
    today = datetime.now().strftime("%Y-%m-%d")

    page.goto("https://pro.planity.com/agenda", wait_until="networkidle", timeout=30000)

    rdv_elements = page.query_selector_all(
        "[class*='appointment'], [class*='rdv'], [class*='event'], [data-appointment]"
    )
    print(f"Nombre de RDV trouvés : {len(rdv_elements)}")

    for i, rdv_el in enumerate(rdv_elements):
        try:
            rdv_el.click()
            page.wait_for_timeout(1500)

            rdv_data = extract_rdv_data(page, today)
            if rdv_data:
                rdvs.append(rdv_data)
                print(f"RDV {i+1} extrait : {rdv_data.get('client', 'inconnu')}")

            close_btn = page.query_selector(
                "button.close, [aria-label='Close'], .modal-close, button[class*='close']"
            )
            if close_btn:
                close_btn.click()
            else:
                page.keyboard.press("Escape")
            page.wait_for_timeout(1000)

        except Exception as e:
            print(f"Erreur RDV {i+1}: {e}")
            continue

    return rdvs


def extract_rdv_data(page, today):
    try:
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

        try:
            el = page.query_selector("[class*='client-name'], [class*='clientName'], h3, .rdv-client")
            if el:
                data["client"] = el.inner_text().strip()
        except:
            pass

        try:
            for btn in page.query_selector_all("button[class*='gender'], [class*='sexe'] button, .gender-selector button"):
                cls = btn.get_attribute("class") or ""
                if "active" in cls or btn.get_attribute("aria-selected") == "true":
                    data["sexe"] = btn.inner_text().strip()
                    break
        except:
            pass

        try:
            el = page.query_selector("input[placeholder*='postal'], input[name*='postal'], [class*='postal']")
            if el:
                data["code_postal"] = el.input_value() or el.inner_text().strip()
        except:
            pass

        try:
            el = page.query_selector("[class*='prestation'], [class*='service-name'], .appointment-service")
            if el:
                data["prestation"] = el.inner_text().strip()
        except:
            pass

        try:
            el = page.query_selector("[class*='collaborator'], [class*='practitioner'], .staff-name")
            if el:
                data["collaboratrice"] = el.inner_text().strip()
        except:
            pass

        try:
            el = page.query_selector("[class*='duration'], [class*='duree']")
            if el:
                duree_text = el.inner_text().strip()
                if "h" in duree_text:
                    parts = duree_text.replace("min", "").split("h")
                    h = int(parts[0]) if parts[0] else 0
                    m = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                    data["duree_min"] = h * 60 + m
                else:
                    data["duree_min"] = int(duree_text.replace("min", "").strip())
        except:
            pass

        try:
            el = page.query_selector("[class*='price'], [class*='prix'], [class*='amount']")
            if el:
                prix_text = el.inner_text().strip().replace("€", "").replace(",", ".").strip()
                data["prix"] = float(prix_text)
        except:
            pass

        try:
            el = page.query_selector("[class*='room'], [class*='cabine'], [class*='cabin']")
            if el:
                data["cabine"] = el.inner_text().strip()
        except:
            pass

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

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page()
        try:
            login_planity(page)
            rdvs = get_today_appointments(page)

            if rdvs:
                success = send_to_n8n(rdvs, today)
                if success:
                    print(f"✅ {len(rdvs)} RDVs envoyés à n8n avec succès!")
                else:
                    print("❌ Erreur envoi n8n")
            else:
                print("Aucun RDV trouvé aujourd'hui")
                send_to_n8n([], today)

        except Exception as e:
            print(f"ERREUR CRITIQUE: {e}")
            import traceback
            traceback.print_exc()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
