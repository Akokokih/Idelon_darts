"""Portable, local analysis bundles. Exporting never sends files anywhere."""
from pathlib import Path
import csv,hashlib,io,json,re,zipfile
from .calibration import external_directory


def export_session(directory,destination):
    root=Path(directory).resolve();destination=external_directory(destination)
    if not (root/'state.json').is_file():raise ValueError('Choisissez un dossier de série contenant state.json.')
    if destination.is_relative_to(root):raise ValueError('Placez le ZIP à l’extérieur de la série.')
    state=json.loads((root/'state.json').read_text(encoding='utf-8'))
    rows=[]
    for result in state.get('results',[]):
        output=result.get('output','');attempt=Path(output).name
        if not re.fullmatch(r'attempt-\d{4,}',attempt):raise ValueError('Référence de tir invalide')
        file=root/attempt/'test.json'
        if file.is_symlink():raise ValueError('Lien symbolique dans la session')
        report=json.loads(file.read_text(encoding='utf-8')) if file.exists() else {}
        obs=report.get('before_observation') or {};receipt=report.get('receipt') or {}
        prediction=report.get('prediction') or {};motion=report.get('angular_motion') or {}
        position=obs.get('launcher_position') or (None,None);target=obs.get('target_center') or (None,None)
        wind=obs.get('wind_features') or (None,None)
        rows.append(dict(number=result['number'],result=result['result'],before_score=result.get('before_score'),
            after_score=result.get('after_score'),lives_lost=result.get('lives_lost'),context=result.get('context'),
            launcher_x=position[0],launcher_y=position[1],target_x=target[0],target_y=target[1],
            wind_x=wind[0],wind_y=wind[1] if len(wind)>1 else 0,visible_angle_rad=obs.get('arm_angle'),
            aim_angle_rad=report.get('aim_angle_rad'),trigger_delay_ns=(report.get('model_at_shot') or {}).get('trigger_delay_ns'),
            frame_sample_ns=obs.get('sample_ns'),capture_start_ns=obs.get('capture_start_ns'),
            capture_end_ns=obs.get('capture_end_ns'),command_ns=prediction.get('release_ns'),
            actual_down_ns=receipt.get('down_ns'),actual_up_ns=receipt.get('up_ns'),
            planned_up_ns=receipt.get('planned_up_ns'),
            up_error_ns=(receipt['up_ns']-receipt['planned_up_ns']
                         if receipt.get('up_ns') is not None and receipt.get('planned_up_ns') is not None else None),
            input_timing_source=receipt.get('source','native-sendinput'),timing_uncertainty_ns=receipt.get('timing_uncertainty_ns'),
            omega_rad_s=motion.get('omega_rad_s'),alpha_rad_s2=motion.get('alpha_rad_s2'),
            fit_residual_rad=motion.get('residual_rad'),impact_tip_y=result.get('tip_y'),
            adapted_delay_ns=result.get('adapted_delay_ns'),evidence=f'{attempt}/test.json'))
    csvfile=io.StringIO(newline='')
    if rows:
        writer=csv.DictWriter(csvfile,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    rate=state.get('rate');percent=f'{rate*100:.1f} %' if rate is not None else 'non mesuré'
    summary=(f'# Série Idleon Darts\n\n{state.get("shots",0)} tirs, {state.get("bullseyes",0)} rouges ({percent}), '
             f'{state.get("lives_lost",0)} vies perdues. État : {state.get("state")}.\n\n'
             'Le taux décrit cette série, sans garantie de 90 %. Les réglages ont pu évoluer pendant les tirs.\n\n'
             '## Pour l’analyse avec Codex\n\n'
             'Auditer la lecture des scores sur les images avant/après. Séparer les données utilisées pour '
             'corriger le modèle et les nouveaux tirs de validation. Comparer les erreurs selon la position, '
             'le vecteur du vent, la vitesse et l’accélération. Examiner les reçus du clic et les horodatages '
             'de capture pour corriger le délai. Ajuster les trajectoires à partir des images de vol disponibles.\n\n'
             '`shots.csv` résume les tirs. Chaque `test.json` contient les observations et le reçu natif. '
             '`flight.json` associe les images de vol aux temps et aux coordonnées de leur recadrage dans la ROI. '
             'Les images de vol peuvent être réduites ; utiliser encoded_width/height pour revenir aux pixels de la ROI. '
             'Les séries anciennes peuvent ne pas contenir de vol. Les pixels manquants ne sont pas reconstitués.\n')
    allowed=re.compile(r'(?:state\.json|session\.json|model-analysis\.md|learned-model\.json|configuration/(?:profile|visual|model|fit-report)\.json|'
                       r'attempt-\d{4,}/(?:test\.json|before(?:-raw)?\.png|after(?:-raw)?\.png|flight\.json|flight/frame-\d{3}\.png))')
    files=[]
    for file in root.rglob('*'):
        if file.is_symlink():raise ValueError('Lien symbolique dans la session')
        if file.is_file() and allowed.fullmatch(file.relative_to(root).as_posix()):files.append(file)
    destination.parent.mkdir(parents=True,exist_ok=True)
    manifest=[]
    # Exclusive creation protects a previous export from accidental replacement.
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(files):
            name=file.relative_to(root).as_posix();data=file.read_bytes()
            archive.writestr(name,data);manifest.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        archive.writestr('shots.csv',csvfile.getvalue().encode('utf-8-sig'))
        archive.writestr('ANALYSIS.md',summary)
        archive.writestr('manifest.json',json.dumps(dict(schema_version=1,bundle_type='idleon-darts-analysis',
            files=manifest),indent=2))
    return dict(kind='export',archive=str(destination),shots=state.get('shots',0),inputs_sent=False)
