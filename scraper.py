import os
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import stealth_sync
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

# ============================================================
# CONFIG — via variables d'environnement Railway
# ============================================================
PLANITY_EMAIL = os.environ.get("PLANITY_EMAIL")
PLANITY_PASSWORD = os.environ.get("PLANITY_PASSWORD")
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL")


def login_planity(page):
    print("Connexion à Planity...")
    page.goto("https://pro.planity.com", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    # Fermer tout bandeau cookie/RGPD qui pourrait bloquer les interactions
    for sel in [
        "button:has-text('Accepter')", "button:has-text('Accept')",
        "button:has-text('J\\'accepte')", "button:has-text('OK')",
        "[id*='cookie'] button", "[class*='cookie'] button",
        "[id*='consent'] button", "[class*='consent'] button",
    ]:
        try:
            page.click(sel, timeout=1500)
            page.wait_for_timeout(500)
        except Exception:
            pass

    # Remplir email avec fill() — pas besoin de clic préalable
    email_sel = "input[type='email'], input[name='email']"
    page.wait_for_selector(email_sel, state="visible", timeout=15000)
    page.fill(email_sel, PLANITY_EMAIL)
    page.wait_for_timeout(800)

    # Afficher le champ mot de passe si nécessaire
    if not page.is_visible("input[type='password']"):
        page.keyboard.press("Tab")
        page.wait_for_timeout(1500)
    if not page.is_visible("input[type='password']"):
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)
    for sel in ["input[type='submit']", "[role='button']", "a[class*='button']", "a[class*='btn']"]:
        if page.is_visible("input[type='password']"):
            break
        try:
            page.click(sel, timeout=1500)
            page.wait_for_timeout(1500)
        except Exception:
            pass

    page.wait_for_selector("input[type='password']", state="visible", timeout=15000)
    page.fill("input[type='password']", PLANITY_PASSWORD)
    page.keyboard.press("Enter")

    # Attendre que le formulaire disparaisse = login accepté
    try:
        page.wait_for_selector("input[type='password']", state="hidden", timeout=30000)
        print("Login accepté, chargement du dashboard...")
        page.wait_for_timeout(4000)
    except Exception:
        page.wait_for_timeout(5000)
    print("Connecté !")


def get_today_appointments(page):
    print("Récupération des RDV du jour...")
    rdvs = []
    today = datetime.now().strftime("%Y-%m-%d")

    # Après login on est déjà sur l'agenda (pro.planity.com/)
    print(f"URL actuelle: {page.url}")

    # Attendre que le calendrier soit chargé (input password disparu = on n'est plus sur login)
    try:
        page.wait_for_selector("input[type='password']", state="hidden", timeout=10000)
        page.wait_for_timeout(3000)
    except Exception:
        page.wait_for_timeout(5000)

    # Debug large : texte du body + compte d'éléments
    page_debug = page.evaluate("""() => {
        const allTexts = [];
        document.querySelectorAll('*').forEach(el => {
            const t = (el.innerText || '').trim();
            if (t.length > 2 && t.length < 50 && !allTexts.includes(t)) allTexts.push(t);
        });
        return {
            url: window.location.href,
            elemCount: document.querySelectorAll('*').length,
            bodySnippet: (document.body ? document.body.innerText : '').substring(0, 300),
            texts: allTexts.slice(0, 40)
        };
    }""")
    print(f"URL: {page_debug['url']} | éléments DOM: {page_debug['elemCount']}")
    print(f"Body: {page_debug['bodySnippet'][:200]}")
    print(f"Textes: {page_debug['texts']}")

    # Chercher des horaires HH:MM - HH:MM SANS filtre couleur (pour debug)
    time_elements = page.evaluate("""() => {
        const timePattern = /\\d{2}:\\d{2}\\s*[-–]\\s*\\d{2}:\\d{2}/;
        const seen = new Set();
        const results = [];
        document.querySelectorAll('*').forEach(el => {
            const text = (el.innerText || '').trim();
            const key = text.substring(0, 60);
            if (timePattern.test(text) && text.length < 250 && !seen.has(key)) {
                seen.add(key);
                const bg = window.getComputedStyle(el).backgroundColor;
                results.push({
                    tag: el.tagName,
                    cls: el.className.substring(0, 100),
                    text: text.substring(0, 100),
                    bg,
                    childCount: el.children.length
                });
            }
        });
        return results.slice(0, 40);
    }""")

    print(f"=== Éléments avec horaires (sans filtre couleur) : {len(time_elements)} ===")
    for el in time_elements:
        print(f"  <{el['tag']}> children={el['childCount']} bg={el['bg']} | txt='{el['text'][:70]}'")
    print(f"Nombre de RDV trouvés : {len(time_elements)}")

    # Identifier les blocs feuilles (sans enfants ou peu d'enfants) avec fond coloré
    rdv_info = [
        el for el in time_elements
        if el['childCount'] <= 5
        and el['bg'] not in ('rgba(0, 0, 0, 0)', 'transparent', 'rgb(255, 255, 255)', 'rgb(242, 242, 242)', 'rgb(250, 250, 250)')
    ]

    rdv_elements = []
    if rdv_info:
        # Récupérer les éléments Playwright à partir de la première classe commune détectée
        first_cls = rdv_info[0].get("cls", "").split()[0] if rdv_info[0].get("cls") else ""
        if first_cls:
            rdv_elements = page.query_selector_all(f".{first_cls}")

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
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )
        page = context.new_page()
        # Masquer les signaux de bot (webdriver, chrome runtime, plugins)
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['fr-FR', 'fr', 'en-US']});
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
        """)
        if HAS_STEALTH:
            stealth_sync(page)
            print("Stealth activé")
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
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
