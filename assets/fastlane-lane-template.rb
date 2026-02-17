platform :ios do
  desc "ASO metadata sync (no binary upload)"
  lane :aso_metadata_sync do
    deliver(
      app_identifier: "com.example.app",
      metadata_path: "fastlane/metadata",
      skip_binary_upload: true,
      skip_screenshots: false,
      force: true
    )
  end
end

platform :android do
  desc "ASO metadata sync (no binary upload)"
  lane :aso_metadata_sync do
    supply(
      package_name: "com.example.app",
      metadata_path: "fastlane/metadata/android",
      skip_upload_apk: true,
      skip_upload_aab: true,
      skip_upload_changelogs: true
    )
  end
end
