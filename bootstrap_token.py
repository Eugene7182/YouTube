from google_auth_oauthlib.flow import InstalledAppFlow
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
def main():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    print("----- COPY BELOW TO RENDER AS YOUTUBE_TOKEN_JSON -----")
    print(creds.to_json())
    print("----- END -----")
if __name__ == "__main__":
    main()
