import youtube_transcript_api
import os

print("\n🕵️ ENQUÊTE EN COURS...")
print(f"Le module est chargé depuis ici : {youtube_transcript_api.__file__}")

# Vérification du dossier actuel
current_dir = os.getcwd()
conflict = os.path.join(current_dir, "youtube_transcript_api.py")
if os.path.exists(conflict):
    print(f"⚠️ ALERTE : J'ai trouvé un fichier conflit ici : {conflict}")
    print("👉 C'est lui le coupable ! Il faut le renommer ou le supprimer.")
else:
    print("Pas de fichier conflictuel direct trouvé dans le dossier courant.")